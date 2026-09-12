from __future__ import annotations

import argparse
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pypdf import PdfReader

from savills_archival_url_discovery import SOURCE_KEY
from savills_legacy_aid_capture_recovery import load_progress, now_iso, save_progress

DATA = Path('data')
MANIFEST = DATA / 'source_diagnostics' / 'savills_live_archive_manifest.json'
CDX = 'https://web.archive.org/cdx/search/cdx'
WAYBACK = 'https://web.archive.org/web/{timestamp}id_/{original}'
UA = 'Mozilla/5.0 (compatible; AuctionSniperHistory/1.0; +https://github.com/garethburke5/Commercial-Auction-Sniper)'
POSTCODE_RE = re.compile(r'\b(?:GIR\s?0AA|(?:(?:[A-PR-UWYZ][0-9][0-9A-HJKSTUW]?|[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?)\s?[0-9][ABD-HJLNP-UW-Z]{2}))\b', re.I)
ID_RE = re.compile(r'\b(?:aid|auction(?:\s+id)?|pid|lot(?:\s+id)?)\s*[:=#-]?\s*(\d{1,6})\b', re.I)


def fetch(url, timeout=40, max_bytes=25_000_000):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/json,application/pdf,*/*;q=0.5'})
    with urlopen(req,timeout=timeout) as r:
        return r.read(max_bytes)


def target_dates(year):
    raw=json.loads(MANIFEST.read_text(encoding='utf-8'))
    vals=set()
    for page in raw.get('pages') or []:
        for x in page.get('dates') or []:
            try:d=date.fromisoformat(str(x))
            except ValueError:continue
            if d.year==year:vals.add(d)
    return sorted(vals)


def cdx(pattern,year,limit):
    params=[('url',pattern),('matchType','prefix'),('from',str(year-1)),('to',str(year+1)),('output','json'),('fl','timestamp,original,statuscode,mimetype,digest'),('filter','statuscode:200'),('collapse','urlkey'),('limit',str(limit))]
    q=CDX+'?'+urlencode(params)
    payload=json.loads(fetch(q,50,15_000_000).decode('utf-8','replace'))
    if not payload or len(payload)<2:return [],q
    head=payload[0]
    rows=[dict(zip(head,r)) for r in payload[1:] if isinstance(r,list) and len(r)==len(head)]
    return rows,q


def pdf_text(data):
    try:
        reader=PdfReader(io.BytesIO(data))
        return '\n'.join((p.extract_text() or '') for p in reader.pages[:220])
    except Exception:
        return ''


def contains_date(text,d):
    low=re.sub(r'\s+',' ',text or '').lower()
    forms={d.strftime('%d %B %Y').lstrip('0').lower(),d.strftime('%d/%m/%Y'),d.strftime('%d-%m-%Y'),d.isoformat()}
    return any(x.lower() in low for x in forms)


def run(year=2014,limit=12000,max_docs=300):
    progress=load_progress(); state=progress.setdefault('sources',{}).setdefault(SOURCE_KEY,{})
    state['historically_complete']=False; state['discovery_exhausted']=False
    targets=target_dates(year)
    patterns=['www.savills.co.uk/*','savills.co.uk/*','pdf.euro.savills.co.uk/*']
    rows=[]; queries=[]; errors=[]
    for pat in patterns:
        try:
            found,q=cdx(pat,year,limit); rows.extend(found); queries.append({'pattern':pat,'query':q,'rows':len(found)})
        except Exception as exc: errors.append(f'{pat} :: {type(exc).__name__}: {exc}')
    docs=[]; seen=set()
    for r in rows:
        original=str(r.get('original') or '')
        mime=str(r.get('mimetype') or '').lower()
        low=original.lower()
        if not (low.endswith('.pdf') or 'pdf' in mime):continue
        if not any(k in low for k in ('auction','catalog','results','sale','lot')):continue
        key=(r.get('timestamp'),original)
        if key in seen:continue
        seen.add(key); docs.append(r)
        if len(docs)>=max_docs:break
    clues=[]; checked=0
    for r in docs:
        original=str(r.get('original') or ''); ts=str(r.get('timestamp') or '')
        if not ts:continue
        capture=WAYBACK.format(timestamp=ts,original=original); checked+=1
        try:text=pdf_text(fetch(capture,35,30_000_000))
        except Exception as exc:
            if len(errors)<80:errors.append(f'{capture} :: {type(exc).__name__}: {exc}')
            continue
        matches=[d for d in targets if contains_date(text,d)]
        if not matches:continue
        postcodes=sorted(set(m.group(0).upper() for m in POSTCODE_RE.finditer(text)))[:80]
        ids=sorted(set(m.group(1) for m in ID_RE.finditer(text)),key=lambda x:int(x))[:120]
        if postcodes or ids:
            clues.append({'original':original,'capture':capture,'auction_dates':[d.isoformat() for d in matches],'postcodes':postcodes,'numeric_ids':ids})
    result={'at':now_iso(),'year':year,'route':'wayback-broader-savills-domain-pdf-catalogue-clue-recovery','target_dates':[d.isoformat() for d in targets],'queries':queries,'pdf_candidates':len(docs),'pdf_checked':checked,'documents_with_exact_date_clues':len(clues),'clues':clues[:80],'errors':errors[:80]}
    state['pdf_catalogue_frontier_last_run']=result; state['last_discovery_mode']=result['route']; state['status']='DISCOVERY EXPANSION' if clues else 'LIVE ARCHIVE BLOCKED'
    if not clues:
        state['pdf_catalogue_frontier_last_blocker']={'at':result['at'],'frontier_date':targets[0].isoformat() if targets else None,'route':result['route'],'message':'Broader Savills-owned archived PDF/catalogue enumeration yielded no exact-date address/identifier clues.','next_safe_route':'Search contemporaneous Savills press/news releases and third-party auction result publications by exact sale totals/date to recover property addresses, then require archived first-party Savills corroboration before History V2 persistence.'}
    else:
        state.pop('pdf_catalogue_frontier_last_blocker',None)
        state['next_frontier_repair']='Use recovered PDF postcodes/numeric IDs to query archived Savills LotDetails/LotList/index.php originals and parse exact-date commercial captures.'
    save_progress(progress)
    diag=DATA/'source_diagnostics';diag.mkdir(parents=True,exist_ok=True);stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
    (diag/f'savills_pdf_catalogue_frontier_{year}_{stamp}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,indent=2,ensure_ascii=False));return len(clues)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--year',type=int,default=2014);ap.add_argument('--limit',type=int,default=12000);ap.add_argument('--max-docs',type=int,default=300);a=ap.parse_args();raise SystemExit(0 if run(a.year,a.limit,a.max_docs)>=0 else 1)
