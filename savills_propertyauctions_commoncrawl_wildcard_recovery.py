#!/usr/bin/env python3
from __future__ import annotations

import gzip, json, re
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

PROGRESS=Path('data/historical_backfill_progress.json')
DIAG=Path('data/source_diagnostics/savills_year_gap_recovery.json')
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE=re.compile(r'\b(?:GIR\s?0AA|(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}))\b',re.I)
LOT_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?([A-Z]?\d+[A-Z]?)\b',re.I)
COMMERCIAL_RE=re.compile(r'\b(?:retail|shop|office|industrial|warehouse|commercial|investment|public house|pub|restaurant|bank|garage|development|mixed[- ]?use|freehold ground rent|supermarket|medical|pharmacy)\b',re.I)
INTERESTING_RE=re.compile(r'(?:aid=|pid=|lot|detail|document|brochure|legal|catalog|property)',re.I)
INDEXES=['CC-MAIN-2018-51','CC-MAIN-2018-43','CC-MAIN-2018-34','CC-MAIN-2018-22','CC-MAIN-2018-13','CC-MAIN-2018-05']

def norm_lot(v): return re.sub(r'[^A-Z0-9]','',str(v or '').upper())

def query(session,index,target):
    r=session.get(f'https://index.commoncrawl.org/{index}-index',params={'url':target,'output':'json','filter':'status:200'},timeout=(4,8))
    if r.status_code==404: return []
    r.raise_for_status(); out=[]
    for line in r.text.splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out

def warc(session,rec):
    if not all(rec.get(k) is not None for k in ('filename','offset','length')): return None
    start=int(rec['offset']); end=start+int(rec['length'])-1
    r=session.get('https://data.commoncrawl.org/'+rec['filename'],headers={'Range':f'bytes={start}-{end}'},timeout=(5,12))
    if r.status_code not in (200,206): return None
    raw=r.content
    try: raw=gzip.decompress(raw)
    except Exception: pass
    low=raw.lower(); i=low.find(b'<html')
    if i<0: i=low.find(b'<!doctype html')
    return raw[i:].decode('utf-8','replace') if i>=0 else None

def main():
    p=json.loads(PROGRESS.read_text()); s=p['sources']['Savills Auctions']; gap=s.get('savills_year_gap_last_run') or {}
    master={str(x)[:10] for x in gap.get('master_manifest_dates',[]) if x}
    cats=[c for c in gap.get('revalidated_propertyauctions_catalogues',[]) if str(c.get('date') or '')[:10] in master]
    clue_keys={(str(c.get('auction_date') or '')[:10],norm_lot(c.get('lot_number'))) for c in gap.get('clue_runs',[]) if c.get('auction_date') and c.get('lot_number')}
    ses=requests.Session(); ses.headers.update({'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.8'})
    runs=[]; candidates=[]; fetched=[]; matches=[]; errors=[]
    for cat in cats:
        aid=str(cat.get('aid')); date=str(cat.get('date') or '')[:10]
        targets=[f'www.propertyauctions.com/*AID={aid}*',f'propertyauctions.com/*AID={aid}*',f'www.propertyauctions.com/*aid={aid}*']
        seen=set(); rr={'auction_date':date,'aid':aid,'targets':targets,'records_found':0,'candidate_urls':[]}
        for idx in INDEXES:
            for target in targets:
                try: hits=query(ses,idx,target)
                except Exception as e:
                    errors.append({'aid':aid,'index':idx,'target':target,'error':f'{type(e).__name__}: {e}'}); continue
                for h in hits[:50]:
                    u=str(h.get('url') or '')
                    if u in seen: continue
                    seen.add(u); rr['records_found']+=1
                    if INTERESTING_RE.search(u):
                        rec={k:h.get(k) for k in ('url','timestamp','status','mime','filename','offset','length','digest')}; rec.update({'index':idx,'aid':aid,'auction_date':date}); candidates.append(rec); rr['candidate_urls'].append(u)
                    if len(rr['candidate_urls'])>=25: break
                if len(rr['candidate_urls'])>=25: break
            if len(rr['candidate_urls'])>=25: break
        runs.append(rr)
    candidates.sort(key=lambda x:(('LotList.aspx' in str(x.get('url'))),str(x.get('url'))))
    for rec in candidates[:120]:
        item={k:rec.get(k) for k in ('auction_date','aid','index','url','timestamp')}
        try:
            html=warc(ses,rec)
            if not html: item['fetch']='no_html'; fetched.append(item); continue
            text=' '.join(BeautifulSoup(html,'html.parser').stripped_strings)
            lots=sorted({norm_lot(x) for x in LOT_RE.findall(text) if norm_lot(x)})
            pcs=sorted({x.upper() for x in POSTCODE_RE.findall(text)})
            item.update({'fetch':'ok','lots':lots[:40],'postcodes':pcs[:40],'commercial_signal':bool(COMMERCIAL_RE.search(text)),'text_chars':len(text)})
            for lot in lots:
                if (rec['auction_date'],lot) in clue_keys and pcs and item['commercial_signal']:
                    matches.append({'auction_date':rec['auction_date'],'aid':rec['aid'],'lot_number':lot,'postcodes':pcs[:8],'source_url':rec.get('url'),'commoncrawl_index':rec.get('index')})
            fetched.append(item)
        except Exception as e:
            item['fetch_error']=f'{type(e).__name__}: {e}'; fetched.append(item)
    at=datetime.now(timezone.utc).isoformat()
    diag={'at':at,'route':'savills-2018-propertyauctions-commoncrawl-wildcard-aid-query-variant-recovery','target_year':2018,'catalogues_attempted':len(cats),'wildcard_candidate_records':len(candidates),'warc_candidates_fetched':len(fetched),'deterministic_date_lot_postcode_commercial_matches':len(matches),'canonical_events_added':0,'runs':runs,'fetches':fetched[:120],'matches':matches[:120],'error_samples':errors[:50]}
    s['savills_year_gap_commoncrawl_wildcard_last_run']=diag; s['last_discovery_mode']=diag['route']; s['historically_complete']=False; s['discovery_exhausted']=False
    if matches:
        msg=f"Wildcard Common Crawl AID/query-variant recovery found {len(candidates)} archived candidate records, fetched {len(fetched)}, and recovered {len(matches)} deterministic date+lot+postcode+commercial identity candidates; promotion awaits full-address/result reconciliation."
        nxt='Reconcile wildcard WARC identities to exact first-party Savills catalogue tuples and promote only complete full-address commercial/mixed-use events.'
    else:
        msg=f"Wildcard Common Crawl AID/query-variant recovery found {len(candidates)} archived candidate records across {len(cats)} master-manifest catalogues, fetched {len(fetched)} candidates, but recovered 0 deterministic date+lot+postcode+commercial identities."
        nxt='Probe archived PropertyAuctions image/file/document asset paths and first-party Savills PDF/catalogue namespaces keyed by exact AID+lot, then reconcile any explicit full-address evidence to the result tuple.'
    s['savills_year_gap_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':'www.propertyauctions.com/*AID=<2018 catalogue AID>*','message':msg,'next_safe_route':nxt}
    p['updated_at']=at; PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False))
    d=json.loads(DIAG.read_text()) if DIAG.exists() else {}; d['commoncrawl_wildcard_run']=diag; DIAG.write_text(json.dumps(d,indent=2,ensure_ascii=False))
    print(json.dumps({k:v for k,v in diag.items() if k not in ('runs','fetches','matches','error_samples')},indent=2))
if __name__=='__main__': main()
