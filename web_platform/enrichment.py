"""Refresh exact-lot gallery and fee evidence without changing the live lot corpus.

Ordered, explicitly scoped source galleries only. Never ranks or replaces heroes.
Failures preserve previously captured evidence. No browser/session/private data.
"""
import argparse
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(__file__).with_name('property_evidence.json')
FAILURES = {}
FAILURE_LOCK = threading.Lock()
BAD_IMAGE = re.compile(r'floor[ _-]?plan|site[ _-]?plan|\bepc\b|\bmap\b|logo|branding', re.I)
SELECTORS = {
 'auctionestates.co.uk': '.lot-thumbnail-image',
 'pugh-auctions.com': 'a[data-id="property-images"]',
 'auctionhouse.co.uk': '#carousel-lot-images .item img',
 'bidx1.com': 'a[data-pswp-photo-index]',
 'barnardmarcusauctions.co.uk': '.lot-details__gallery-carousel .lot-gallery__item img',
 'futurepropertyauctions.co.uk': '.item img[src*="/upload/"]',
 'symondsandsampson.co.uk': 'a[href*="cdn.webdadi.net/Media/image/"], img[alt^="Property Image"]',
}

def public_url(url, base):
    if not url or not str(url).strip():return None
    value = urljoin(base, str(url or ''))
    p = urlsplit(value)
    return value if p.scheme in ('https','http') and p.hostname and not p.username else None


def image_key(url):
    p = urlsplit(url)
    # Ignore cache/resize rendition suffixes, while retaining actual image identity.
    return re.sub(r'_web_(?:small|medium|large)$', '', p.netloc.lower()+p.path)


def ordered_images(values, base, primary=None):
    output=[];seen=set()
    for value in values:
        item = value if isinstance(value,dict) else {'url':value}
        url=public_url(item.get('url'),base)
        if not url or image_key(url)==image_key(base) or BAD_IMAGE.search(url+' '+str(item.get('label') or '')):
            continue
        k=image_key(url)
        if k in seen or (primary and k==image_key(primary)):
            continue
        seen.add(k);output.append({'url':url,'label':str(item.get('label') or 'Source gallery image')})
    return output


def lot_fee(text, host):
    """Recognise narrow, explicit source clauses. Never parse deposit amounts."""
    text=re.sub(r'\s+',' ',text)
    if 'bidx1.com' in host:
        m=re.search(r"A Buyer[’']s Fee of £([\d,]+(?:\.\d+)?) \(inclusive of VAT\)",text,re.I)
        if m:return {'bands':[{'fixed':float(m[1].replace(',','')),'vat':'included'}]},m[0]
    if 'pugh-auctions.com' in host:
        m=re.search(r"Buyer[’']s Fee of ([\d.]+)% inc\.? VAT of the purchase price \(subject to a minimum of £([\d,.]+) inc\.? VAT\)",text,re.I)
        if m:return {'bands':[{'rate':float(m[1])/100,'minimum':float(m[2].replace(',','')),'vat':'included'}]},m[0]
    if 'auctionhouselondon.co.uk' in host:
        premium=re.search(r"Buyers?[’']? Premium of £([\d,]+(?:\.\d+)?) inc\.? VAT.*?in addition to the buyer[’']s admin fee of £([\d,]+(?:\.\d+)?) inc\.? VAT",text,re.I)
        if premium:return {'bands':[{'fixed':sum(float(v.replace(',','')) for v in premium.groups()),'vat':'included'}]},premium[0]
        m=re.search(r'Administration Fee\s*[:–-]?\s*£([\d,]+(?:\.\d+)?).*?(?:including|inc\.?)\s*VAT',text,re.I)
        if m and len(m[0])<220:return {'bands':[{'fixed':float(m[1].replace(',','')),'vat':'included'}]},m[0]
    if 'auctionhouse.co.uk' in host:
        match=re.search(r'Additional Fees\s+(.*?)(?:Disbursements|View Larger Map|Disclaimer:)',text,re.I)
        if match:
            excerpt=match[1].strip()
            chunks=re.split(r'(?=(?:Administration Charge|Buyer[’\']s Premium|Searches)\s*[-:])',excerpt,flags=re.I)
            fixed=rate=minimum=0;found=0
            for chunk in chunks:
                chunk=chunk.strip()
                if not chunk:continue
                variable=re.match(r'(?:Administration Charge|Buyer[’\']s Premium)\s*[-:]\s*([\d.]+)% inc\.? VAT of the purchase price,? subject to a minimum of £([\d,.]+) inc\.? VAT',chunk,re.I)
                flat=re.match(r'(?:Administration Charge|Buyer[’\']s Premium|Searches)\s*[-:]\s*£([\d,.]+)\s*(?:\(?inc(?:luding)?\.? VAT\)?)',chunk,re.I)
                if variable and not rate:
                    rate=float(variable[1])/100;minimum=float(variable[2].replace(',',''));found+=1
                elif flat:
                    fixed+=float(flat[1].replace(',',''));found+=1
                else:return None,None  # An unresolved extra component forbids a partial total.
            if found:return {'bands':[{'fixed':fixed,'rate':rate,'minimum':minimum,'vat':'included'}]},excerpt
    return None,None


def extract_html(raw, row):
    url=row['url'];host=urlsplit(url).hostname or '';s=BeautifulSoup(raw,'html.parser')
    values=[];sections=[]
    if 'auctions.savills.co.uk' in host:
        match=re.search(r"lot:\s*JSON.parse\('((?:\\.|[^'])*)'\)",raw)
        if match:
            detail=json.loads(json.loads('"'+match[1].replace("\\'", "'")+'"'))
            # Exact lot identity, excluding agents, tours and related properties.
            if str(detail.get('id')) == url.rstrip('/').split('-')[-1]:
                values=[{'url':urljoin('https://resize.auctions.savills.co.uk/',i['large_image']),
                         'label':'Auctioneer gallery image'} for i in sorted(detail.get('images',[]),key=lambda i:int(i.get('ordering') or 0)) if i.get('large_image')]
                sections=[{'title':title,'text':BeautifulSoup(detail[field],'html.parser').get_text('\n',strip=True)} for field,title in [('description','Description'),('strapline','Key Investment Points')] if detail.get(field)]
    for domain,selector in SELECTORS.items():
        if host==domain or host.endswith('.'+domain):
            for e in s.select(selector):
                img=e if e.name=='img' else e.find('img')
                src=e.get('href') if e.name=='a' else e.get('data-src') or e.get('data-lazy') or e.get('src')
                values.append({'url':src,'label':e.get('title') or (img.get('alt') if img else '')})
    if 'auctionhouselondon.co.uk' in host:
        from collectors.auction_house_london_detail import _embedded_lot
        detail=_embedded_lot(s,url)
        values=detail.get('images',[])
        sections=[{'title':x['name'],'text':BeautifulSoup(x['content'],'html.parser').get_text('\n',strip=True)} for x in detail.get('lotData',[]) if x.get('content')]
        if detail.get('description'):sections.insert(0,{'title':'Description','text':BeautifulSoup(detail['description'],'html.parser').get_text('\n',strip=True)})
    if 'auctionestates.co.uk' in host:
        for selector,title in (('#details','Description'),('#tenure','Tenure'),('#epc','EPC')):
            node=s.select_one(selector)
            if node:
                content=re.split(r'Viewings\s+Contact Auction Estates|Important notices|Conditions of Sale',node.get_text('\n',strip=True),maxsplit=1,flags=re.I)[0]
                sections.append({'title':title,'text':content})
    fee,excerpt=lot_fee(s.get_text(' ',strip=True),host)
    logos=[]
    for e in s.select('img'):
        src=e.get('src') or e.get('data-src') or ''
        label=(e.get('alt') or '')+' '+src
        if 'logo' in label.lower() and not re.search(r'trustpilot|rics|ombudsman|facebook|instagram|partner|twitter|youtube|linkedin',label,re.I):
            logo=public_url(src,url)
            if logo:logos.append(logo)
    return {'gallery':ordered_images(values,url,row.get('image_url')),'sections':sections,
            'fee_calculation':fee,'fee_excerpt':excerpt,'logo_url':logos[0] if logos else None}


def fetch(row):
    url=row['url'];host=urlsplit(url).hostname or ''
    if host=='www.allsop.co.uk':
        source='https://www.allsop.co.uk/api/lot/reference/'+url.rstrip('/').split('/')[-1]
        response=requests.get(source,timeout=(8,25));response.raise_for_status();detail=response.json()
        images=sorted([i for i in detail.get('images',[]) if not i.get('deleted') and i.get('file_id')],key=lambda i:float(i.get('sort_order') or 0))
        values=[{'url':'https://www.allsop.co.uk/api/image/'+i['file_id']+'/884/497','label':i.get('title') or i.get('type')} for i in images]
        result={'gallery':ordered_images(values,url,row.get('image_url'))}
        version=detail.get('version') or {}
        result['sections']=[{'title':title,'text':'\n'.join(BeautifulSoup(str(x.get('value') or ''),'html.parser').get_text(' ',strip=True) for x in version.get(field,[]))} for field,title in [('features','Key Investment Points'),('description','Description'),('accommodation_bullets','Accommodation'),('tenure_bullets','Tenure')] if version.get(field)]
    elif any(host==d or host.endswith('.'+d) for d in SELECTORS) or host in ('auctionhouselondon.co.uk','auctions.savills.co.uk'):
        source=url.replace('http:','https:',1)
        response=requests.get(source,timeout=(8,22));response.raise_for_status()
        result=extract_html(response.text,row)
    else:return None
    result.update(source_url=url,evidence_url=source,checked_on=datetime.now(timezone.utc).date().isoformat(),response_sha256=hashlib.sha256(response.content).hexdigest())
    return result


def bounded_fetch(row):
    host=urlsplit(row['url']).hostname
    with FAILURE_LOCK:
        if FAILURES.get(host,0)>=3:return None
    try:
        result=fetch(row)
        with FAILURE_LOCK:FAILURES[host]=0
        return result
    except requests.RequestException:
        with FAILURE_LOCK:FAILURES[host]=FAILURES.get(host,0)+1
        raise


def save_evidence(doc):
    temporary=EVIDENCE.with_suffix('.tmp')
    temporary.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(EVIDENCE)


def refresh(limit=1200,force=False):
    doc=json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else {'schema_version':1,'properties':{}}
    rows=json.loads((ROOT/'data/properties.json').read_text())['properties']
    cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).date().isoformat()
    todo=[r for r in rows if force or doc['properties'].get(r['url'],{}).get('checked_on','')<cutoff][:limit]
    ok=failed=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        pending={pool.submit(bounded_fetch,row):row for row in todo}
        for future in as_completed(pending):
            row=pending[future]
            try:
                result=future.result()
                if result:
                    old=doc['properties'].get(row['url'],{})
                    # A degraded fetch must not erase a previously recovered gallery.
                    if not result.get('gallery') and old.get('gallery'):result['gallery']=old['gallery']
                    if result.get('gallery')==old.get('gallery') and old.get('response_sha256')!=result.get('response_sha256'):
                        result['additional_evidence']=[{k:old.get(k) for k in ('evidence_url','checked_on','response_sha256')}]
                    doc['properties'][row['url']]=result;ok+=1
            except (requests.RequestException,ValueError,KeyError,TypeError) as e:
                failed+=1
                print('Unchanged:',row['source'],type(e).__name__,flush=True)
            if (ok+failed)%50==0:
                save_evidence(doc)
                print(f'Checkpoint: {ok} lot pages checked, {failed} fetch failures',flush=True)
    save_evidence(doc)
    print(json.dumps({'checked':ok,'failed':failed,'stored':len(doc['properties']),
        'with_gallery':sum(bool(x.get('gallery')) for x in doc['properties'].values()),
        'with_lot_fee':sum(bool(x.get('fee_calculation')) for x in doc['properties'].values())}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=1200);parser.add_argument('--force',action='store_true')
    args=parser.parse_args();refresh(args.limit,args.force)
