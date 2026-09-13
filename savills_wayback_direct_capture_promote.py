from __future__ import annotations
import json,re
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlunsplit
import requests
from bs4 import BeautifulSoup
from history_database import update_history_database

SOURCE='Savills Auctions'
P=Path('data/historical_backfill_progress.json')
H=Path('data/property_history.json')
D=Path('data/source_diagnostics/savills_wayback_direct_capture_promotion.json')
SRC=Path('data/source_diagnostics/savills_wayback_older_auc_recovery.json')
CDX='https://web.archive.org/cdx/search/cdx'
LOT='http://auctions.savills.co.uk/commercial/comm_previous_auction_lot.asp'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
AUC_RE=re.compile(r'(?:[?&]|&amp;)auc=(\d+)',re.I)
POS_RE=re.compile(r'(?:[?&]|&amp;)pos=(\d+)',re.I)
POSTCODE_RE=re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b',re.I)
LOTNO_RE=re.compile(r'\bLot\s*(?:No\.?\s*)?(\d+[A-Z]?)\b',re.I)
COMMERCIAL_RE=re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use|ground rent|leisure)\b',re.I)
MONEY=r'£\s*([0-9][0-9,]*(?:\.\d+)?)\s*([MK])?'
RESULT_RE=re.compile(r'\bResult\s*:?\s*'+MONEY,re.I)
GUIDE_RE=re.compile(r'\bGuide\s*Price\s*:?\s*'+MONEY,re.I)
RENT_RE=re.compile(r'(?:Current\s+Rent\s+Reserved|Rent\s+Reserved|Current\s+Rent|Rent)\s*:?\s*'+MONEY+r'\s*(?:p\.?a\.?|pa|per annum)',re.I)
TENURE_RE=re.compile(r'\bTenure\s+(Freehold|Leasehold)\b',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def cash(num,suffix):
    if not num:return None
    v=float(num.replace(',','')); s=(suffix or '').upper()
    if s=='M':v*=1_000_000
    elif s=='K':v*=1_000
    return int(round(v))
def qint(url,name):
    m=re.search(r'(?:[?&]|&amp;)'+re.escape(name)+r'=(\d+)',url or '',re.I)
    return int(m.group(1)) if m else None
def parse_date(url):
    q=parse_qs(urlsplit((url or '').replace('&amp;','&')).query)
    raw=(q.get('date') or q.get('Date') or [None])[0]
    if not raw:return None
    for fmt in ('%d/%m/%Y','%d-%m-%Y'):
        try:return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:pass
    return None

def cdx_lot_namespace():
    params={'url':LOT,'matchType':'prefix','output':'json','fl':'timestamp,original,statuscode,mimetype,digest','filter':'statuscode:200','to':'20100509','collapse':'urlkey','limit':'20000'}
    r=requests.get(CDX,params=params,headers={'User-Agent':UA,'Connection':'close'},timeout=(8,60));r.raise_for_status();data=r.json()
    return data[1:] if isinstance(data,list) and data and isinstance(data[0],list) else (data if isinstance(data,list) else [])

def replay_variants(ts,orig):
    p=urlsplit(orig); hosts=[p.netloc,p.netloc.replace(':80','')]
    if not p.netloc.startswith('www.'):hosts.append('www.'+p.netloc.replace(':80',''))
    out=[]
    for scheme in ('http','https'):
        for host in hosts:
            o=urlunsplit((scheme,host,p.path,p.query,''))
            for mod in ('id_','if_',''):
                out.append(f'https://web.archive.org/web/{ts}{mod}/{o}')
    return list(dict.fromkeys(out))

def replay_capture(row,date_map):
    ts,orig=row[0],row[1];auc=qint(orig,'auc');pos=qint(orig,'pos');ad=date_map.get(auc)
    attempts=[]
    for u in replay_variants(ts,orig):
        try:
            r=requests.get(u,headers={'User-Agent':UA,'Connection':'close'},timeout=(5,18),allow_redirects=True)
            attempts.append({'url':u,'status':r.status_code,'bytes':len(r.content)})
            if r.status_code!=200 or len(r.content)<250:continue
            soup=BeautifulSoup(r.text,'html.parser');text=' '.join(soup.stripped_strings)
            lotm=LOTNO_RE.search(text)
            return {'timestamp':ts,'original':orig,'auc':auc,'pos':pos,'auction_date':ad,'replay_url':u,'status':200,'text':text[:16000],'lot_number':lotm.group(1).upper() if lotm else None,'headings':[' '.join(x.stripped_strings)[:700] for x in soup.find_all(['h1','h2','h3','h4','strong']) if ' '.join(x.stripped_strings)][:100],'attempts':attempts}
        except Exception as e:attempts.append({'url':u,'error':f'{type(e).__name__}: {e}'})
    return {'timestamp':ts,'original':orig,'auc':auc,'pos':pos,'auction_date':ad,'status':None,'attempts':attempts}

def address(rec):
    for h in rec.get('headings') or []:
        if POSTCODE_RE.search(h) and not re.search(r'Solicitor|Seller|E-mail|Tel|Fax',h,re.I):return re.sub(r'\s+',' ',h).strip(' •')
    t=rec.get('text') or ''
    m=re.search(r'\bMap\s+\S+\s+(.{8,260}?'+POSTCODE_RE.pattern+r')(?:\s+[•]|\s+Freehold|\s+Leasehold)',t,re.I)
    return re.sub(r'\s+',' ',m.group(1)).strip(' •') if m else None
def ptype(rec):
    for h in rec.get('headings') or []:
        if COMMERCIAL_RE.search(h) and ('•' in h or re.search(r'\b(?:Freehold|Leasehold)\b',h,re.I)):return re.sub(r'^\s*[•·-]+\s*','',re.sub(r'\s+',' ',h)).strip()
    t=rec.get('text') or ''
    m=re.search(r'[•·]\s*((?:Freehold|Leasehold)\s+[^•]{1,140}?(?:Investment|Retail|Shop|Bank|Office|Industrial|Warehouse|Restaurant|Commercial|Mixed[- ]Use|Ground Rent|Leisure))\b',t,re.I)
    return re.sub(r'\s+',' ',m.group(1)).strip() if m else None
def row_from(rec):
    if rec.get('status')!=200:return None,'replay-not-200'
    if not rec.get('auction_date'):return None,'missing-auction-date-map'
    t=re.sub(r'\s+',' ',rec.get('text') or '');lot=str(rec.get('lot_number') or '').strip();addr=address(rec);typ=ptype(rec);result=RESULT_RE.search(t)
    if not lot:return None,'missing-lot-number'
    if not addr or not POSTCODE_RE.search(addr):return None,'missing-full-address'
    if not typ or not COMMERCIAL_RE.search(typ):return None,'not-explicitly-commercial-or-mixed'
    if not result:return None,'missing-explicit-result'
    sale=cash(result.group(1),result.group(2));guide=GUIDE_RE.search(t);rent=RENT_RE.search(t);ten=TENURE_RE.search(t);annual=cash(rent.group(1),rent.group(2)) if rent else None
    return {'source':SOURCE,'url':rec['original'],'source_id':f'legacy-direct-auc{rec["auc"]}-pos{rec["pos"]}','auction_date':rec['auction_date'],'lot_number':lot,'address':addr,'status':'SOLD','guide_price':cash(guide.group(1),guide.group(2)) if guide else None,'sale_price':sale,'annual_rent':annual,'gross_yield':round(annual/sale*100,2) if annual and sale else None,'tenure':ten.group(1).title() if ten else None,'property_type':typ,'description':f'Recovered from a first-party Savills Auctions lot capture archived by the Internet Archive. Archived replay: {rec.get("replay_url")}'},None

def main():
    p=json.loads(P.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
    before=sum(1 for e in json.loads(H.read_text()).get('auction_events',[]) if e.get('source')==SOURCE)
    src=json.loads(SRC.read_text()) if SRC.exists() else {}
    date_map={}
    for rep in src.get('replays') or []:
        auc=rep.get('auc') or qint(rep.get('original',''),'auc');ad=parse_date(rep.get('original',''))
        if auc and ad:date_map[int(auc)]=ad
    errors=[]
    try:namespace_rows=cdx_lot_namespace()
    except Exception as e:namespace_rows=[];errors.append({'route':LOT,'error':f'{type(e).__name__}: {e}'})
    captures=[];seen=set()
    for row in namespace_rows:
        if len(row)<2:continue
        auc=qint(row[1],'auc');pos=qint(row[1],'pos')
        if not auc or auc==675 or not pos or auc not in date_map:continue
        key=(auc,pos,row[0],row[1])
        if key in seen:continue
        seen.add(key);captures.append(row)
    pages=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for f in as_completed([ex.submit(replay_capture,r,date_map) for r in captures]):pages.append(f.result())
    pages.sort(key=lambda x:(x.get('auction_date') or '',x.get('auc') or 0,x.get('pos') or 0))
    rows=[];rejected=[];rowseen=set()
    for rec in pages:
        row,reason=row_from(rec)
        if reason:rejected.append({'date':rec.get('auction_date'),'auc':rec.get('auc'),'pos':rec.get('pos'),'reason':reason});continue
        key=(row['auction_date'],row['lot_number'],row['address'].lower())
        if key in rowseen:continue
        rowseen.add(key);rows.append(row)
    db=update_history_database(rows,path=H);after=sum(1 for e in db.get('auction_events',[]) if e.get('source')==SOURCE);added=after-before;at=now()
    diag={'at':at,'route':'savills-wayback-direct-cdx-capture-reuse','namespace_rows':len(namespace_rows),'dated_auc_ids':len(date_map),'direct_captures_attempted':len(captures),'pages_http_200':sum(1 for x in pages if x.get('status')==200),'validated_rows':len(rows),'canonical_events_before':before,'canonical_events_after':after,'canonical_events_added':added,'errors':errors,'rejected_rows':rejected,'page_results':pages}
    s['savills_wayback_direct_capture_last_run']=diag;s['last_history_event_count']=after;s['lots_captured']=after;s['last_discovery_mode']=diag['route'];s['historically_complete']=False;s['discovery_exhausted']=False
    if added:
        earliest=min(r['auction_date'] for r in rows);prior=s.get('earliest_date_reached');s['earliest_date_reached']=min(prior,earliest) if prior else earliest;s['earliest_month_reached']=s['earliest_date_reached'][:7];s['last_success']=at;s['status']='LIVE ARCHIVE INGESTING'
        msg=f'Reused {len(captures)} actual archived lot capture rows directly instead of repeating exact-CDX lookup; {diag["pages_http_200"]} replayed HTTP 200, {len(rows)} validated rows, {added} new canonical events.'
        nxt='Continue direct archived-capture promotion across every remaining older Auc and enumerate additional pagination/query variants, preserving strict full-address/commercial/result validation.'
    else:
        s['status']='LIVE ARCHIVE BLOCKED';msg=f'Reused {len(captures)} actual archived lot capture rows directly from the namespace rather than exact-CDX lookup; {diag["pages_http_200"]} replayed HTTP 200 but no new canonical rows passed strict validation.'
        nxt='Probe archived detail/result-grid HTML for pagination, form actions, script variables and document/PDF links, then use those captured originals to recover full-address lot evidence without relying on the failing lot replay path.'
    s['propertyauctions_cursor_last_blocker']={'at':at,'route':diag['route'],'failing_url_or_route':LOT+'?Auc=<older>&pos=<n> direct CDX capture rows before 2010-05-10','message':msg,'next_safe_route':nxt}
    p['updated_at']=at;P.write_text(json.dumps(p,indent=2,ensure_ascii=False));D.parent.mkdir(parents=True,exist_ok=True);D.write_text(json.dumps(diag,indent=2,ensure_ascii=False))
    print(json.dumps({'savills_events_before':before,'savills_events_after':after,'canonical_events_added':added,'namespace_rows':len(namespace_rows),'dated_auc_ids':len(date_map),'direct_captures_attempted':len(captures),'pages_http_200':diag['pages_http_200'],'validated_rows':len(rows),'earliest_verified':s.get('earliest_date_reached'),'errors':errors},indent=2))
if __name__=='__main__':main()
