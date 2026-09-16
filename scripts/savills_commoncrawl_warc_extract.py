#!/usr/bin/env python3
"""Retrieve exact Common Crawl WARC byte ranges from the persisted Savills inventory.
Distinct recovery route after CDX enumeration: archived-body extraction.
Does not canonicalise anything; it persists bodies + extraction diagnostics for review.
"""
from __future__ import annotations
import gzip, io, json, pathlib, re, urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[1]
INV=ROOT/'data/historical_raw/savills_commoncrawl_2010_inventory.json'
OUT=ROOT/'data/historical_raw/savills_commoncrawl_2010_bodies.json'
BLOCK=ROOT/'data/source_diagnostics/savills_commoncrawl_warc_body_blocker.json'
BASE='https://data.commoncrawl.org/'
UA='Commercial-Auction-Sniper/1.0 historical-research'

def get_range(filename, offset, length):
    req=urllib.request.Request(BASE+filename,headers={'User-Agent':UA,'Range':f'bytes={offset}-{offset+length-1}'})
    with urllib.request.urlopen(req,timeout=60) as r: return r.read(), r.status

def payload(raw):
    try: dec=gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    except Exception: dec=raw
    # WARC headers then HTTP headers then body.
    parts=re.split(br'\r?\n\r?\n',dec,maxsplit=2)
    return parts[2] if len(parts)>=3 else dec

def main():
    inv=json.loads(INV.read_text())
    unique={}
    for r in inv.get('records',[]):
        if str(r.get('status'))!='200' or not all(r.get(k) for k in ('filename','offset','length','url')): continue
        unique.setdefault(r.get('digest') or r['url'],r)
    rows=[]; errors=[]
    for key,r in unique.items():
        try:
            raw,status=get_range(r['filename'],int(r['offset']),int(r['length']))
            body=payload(raw)
            rows.append({'url':r['url'],'digest':r.get('digest'),'index':r.get('_index'),'warc_filename':r['filename'],'offset':r['offset'],'length':r['length'],'http_status':status,'body_bytes':len(body),'pdf_magic':body.startswith(b'%PDF-'),'body_hex_prefix':body[:16].hex()})
            if body.startswith(b'%PDF-'):
                p=ROOT/'data/historical_raw'/('savills_cc_'+re.sub(r'[^a-z0-9]+','_',pathlib.PurePosixPath(r['url']).name.lower()).strip('_'))
                if not str(p).endswith('.pdf'): p=pathlib.Path(str(p)+'.pdf')
                p.write_bytes(body)
        except Exception as e: errors.append({'url':r.get('url'),'digest':r.get('digest'),'error':type(e).__name__+': '+str(e)})
    OUT.write_text(json.dumps({'route':'common_crawl_exact_warc_range_retrieval','inventory_records':len(inv.get('records',[])),'unique_digests':len(unique),'retrieved':rows,'errors':errors},indent=2))
    BLOCK.write_text(json.dumps({'route':'common_crawl_exact_warc_range_retrieval','retrieved_count':len(rows),'pdf_count':sum(bool(x['pdf_magic']) for x in rows),'error_count':len(errors),'errors':errors,'next_route':'Parse recovered PDFs for auction/lot/address identifiers and reconcile to PropertyAuctions AID/Auc; if WARC range service blocks, use Common Crawl S3/HTTPS full-record retrieval or Wayback archived bodies.'},indent=2))
    print('UNIQUE',len(unique),'RETRIEVED',len(rows),'PDF',sum(bool(x['pdf_magic']) for x in rows),'ERRORS',len(errors))
if __name__=='__main__': main()
