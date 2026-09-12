from __future__ import annotations

import argparse, json, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

from history_database import update_history_database
from savills_archival_url_discovery import SOURCE_KEY, source_count
from savills_legacy_aid_capture_recovery import recover_candidate
from savills_manifest_aid_capture_recovery import unresolved_manifest_dates

PROGRESS=Path('data/historical_backfill_progress.json')
HISTORY=Path('data/property_history.json')
DIAG=Path('data/source_diagnostics/savills_bing_rss_index_recovery.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
SAVILLS='https://auctions.savills.co.uk'

def now(): return datetime.now(timezone.utc).isoformat()
def get(url, timeout=25):
    r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'},timeout=timeout); r.raise_for_status(); return r.text

def rss_urls(query):
    url='https://www.bing.com/search?format=rss&count=50&q='+quote_plus(query)
    try: text=get(url,22)
    except Exception as e: return [], f'{type(e).__name__}: {e}'
    soup=BeautifulSoup(text,'xml')
    return [x.get_text(strip=True) for x in soup.find_all('link') if 'propertyauctions.io/listings/' in x.get_text()], ''

def inspect_listing(url, target):
    try: text=get(url,22)
    except Exception as e: return None, f'fetch {type(e).__name__}: {e}'
    plain=' '.join(BeautifulSoup(text,'html.parser').stripped_strings)
    variants={target.strftime('%d %B %Y'),target.strftime('%-d %B %Y'),target.strftime('%d %B, %Y'),target.strftime('%-d %B, %Y')}
    if not any(v in plain for v in variants): return None,'date absent'
    if not re.search(r'\bSavills(?: plc| Auctions)?\b',plain,re.I): return None,'Savills attribution absent'
    norm=text.replace('\\/','/')
    candidates=set(re.findall(r'https?://auctions\.savills\.co\.uk/(?:Auctions/LotDetails\?[^"\'<>\s]+|auctions/[^"\'<>\s]+)',norm,re.I))
    clues=[]
    for m in re.finditer(r'(?:https?:)?//(?:resize\.)?auctions\.savills\.co\.uk/assets/images/lots/(\d+)/(?:large|medium|small|thumb)/?(\d+)?/[^"\'<>\s]+',norm,re.I):
        aid,lot=m.group(1),m.group(2)
        clues.append({'auction_id':aid,'lot_number':lot,'asset_url':m.group(0)})
        if lot:
            slug=target.strftime('%B-%Y').lower()
            candidates.add(f'{SAVILLS}/auctions/{slug}-{aid}/{lot}')
            candidates.add(f'{SAVILLS}/auctions/{slug}-{aid}/{lot}/')
    return {'url':url,'candidates':sorted(candidates),'image_clues':clues},''

def run(max_dates=12,max_live=220):
    p=json.loads(PROGRESS.read_text()); s=p.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    s['historically_complete']=False; s['discovery_exhausted']=False; s['status']='DISCOVERY EXPANSION'
    dates=sorted(unresolved_manifest_dates(s), reverse=True)[:max_dates]
    before=source_count(json.loads(HISTORY.read_text()))
    discovered=[]; matched=[]; search_errors=[]; rejected=[]
    for d in dates:
        ds=d.strftime('%-d %B %Y')
        queries=[f'site:propertyauctions.io/listings "Savills plc" "{ds}"',f'site:propertyauctions.io/listings "Savills" "Auction Date" "{ds}"']
        for q in queries:
            urls,err=rss_urls(q)
            if err: search_errors.append({'query':q,'error':err})
            for u in urls:
                if u not in discovered: discovered.append(u)
                item,reason=inspect_listing(u,d)
                if item: item['target_date']=d; matched.append(item)
                elif len(rejected)<80: rejected.append({'url':u,'date':d.isoformat(),'reason':reason})
    recovered=[]; checked=0
    seen=set()
    for item in matched:
        for candidate in item['candidates']:
            if candidate in seen or checked>=max_live: continue
            seen.add(candidate); checked+=1
            row,reason=recover_candidate(candidate,item['target_date'],item['url'])
            if row:
                row['archival_discovery_url']=item['url']; recovered.append(row)
    after=before; added=0
    if recovered:
        db=update_history_database(recovered,path=HISTORY); after=source_count(db); added=max(0,after-before)
        s['lots_captured']=after
        if added:
            ed=min(str(r.get('auction_date')) for r in recovered if r.get('auction_date'))
            s['earliest_date_reached']=min(s.get('earliest_date_reached') or ed,ed); s['earliest_month_reached']=s['earliest_date_reached'][:7]
    diag={'at':now(),'route':'bing-rss-propertyauctions-exact-date-to-first-party-savills-validation','dates':[d.isoformat() for d in dates],'indexed_listing_urls':len(discovered),'matched_savills_pages':len(matched),'image_id_clues':sum(len(x['image_clues']) for x in matched),'candidate_first_party_urls':len(seen),'live_checked':checked,'commercial_rows_seen':len(recovered),'canonical_events_added':added,'savills_events_before':before,'savills_events_after':after,'search_errors':search_errors[:80],'matched_samples':matched[:25],'rejected_samples':rejected[:40]}
    s['bing_rss_index_last_run']=diag; s['last_discovery_mode']=diag['route']
    if added==0:
        s['status']='LIVE ARCHIVE BLOCKED'; s['bing_rss_index_last_blocker']={'at':diag['at'],'route':diag['route'],'dates':diag['dates'],'message':'Bing RSS exact-date indexing did not yield a first-party Savills lot page valid for persistence.','next_safe_route':'Enumerate PropertyAuctions Savills listing URLs from its publicly exposed auctioneer/filter application routes or page data rather than search-engine indexes, then validate any recovered first-party Savills source URLs.'}
    else: s.pop('bing_rss_index_last_blocker',None)
    p['updated_at']=now(); PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False)); DIAG.parent.mkdir(parents=True,exist_ok=True); DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False)); print(json.dumps(diag,indent=2,ensure_ascii=False)); return added

if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--max-dates',type=int,default=12); a.add_argument('--max-live-checks',type=int,default=220); x=a.parse_args(); run(x.max_dates,x.max_live_checks)
