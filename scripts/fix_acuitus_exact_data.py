from pathlib import Path
import json

APP = Path('app.py')
s = APP.read_text(encoding='utf-8')

old = '''def _acuitus_current():
    url="https://www.acuitus.co.uk/find-a-property/?clear=y"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if re.search(r"acuitus\.co\.uk/property/\d+/?",href) and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v652_exact_row,u,"Acuitus","2026-09-17","") for u in links[:20]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []
'''

new = '''def _acuitus_exact_row(url):
    """Parse one Acuitus property page without leaking related lots/contact imagery."""
    try:
        raw=fetch(url)
        soup=BeautifulSoup(raw,"lxml")
        full=norm(soup.get_text(" ",strip=True))
        cut=full.lower().find("you may also be interested in")
        text=full[:cut] if cut >= 0 else full

        tt=norm(soup.title.get_text(" ",strip=True)) if soup.title else ""
        parts=[x.strip() for x in tt.split("|")]
        address=parts[1] if len(parts)>=3 and "Acuitus" in parts[-1] else ""
        if not address:
            h1=soup.find("h1")
            address=norm(h1.get_text(" ",strip=True)) if h1 else "Property"

        lm=re.search(r"\bLot\s+(\d+[A-Z]?)\b",text,re.I)
        lot=("Lot "+lm.group(1).upper()) if lm else "Lot TBC"

        gm=re.search(r"Guide\*?\s*(?:£\s*([\d,]+)|Refer\s+to\s+Auctioneer)",text,re.I)
        guide=float(gm.group(1).replace(",","")) if gm and gm.group(1) else None
        guide_status="Refer to Auctioneer" if gm and not gm.group(1) else None

        rm=re.search(r"\bRent\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:per\s+annum|p\.?a\.?|pa)\b",text,re.I)
        rent=float(rm.group(1).replace(",","")) if rm else None
        tenure="Freehold" if re.search(r"\bTenure\s+Freehold\b|\bFreehold\.",text,re.I) else ("Leasehold" if re.search(r"\bTenure\s+Leasehold\b|\bLeasehold\.",text,re.I) else None)

        if re.search(r"Not\s+elected\s+for\s+VAT",text,re.I):
            vat="Not elected"
        elif re.search(r"VAT\s+is\s+applicable\s+to\s+this\s+lot|VAT\s+applicable|subject\s+to\s+VAT",text,re.I):
            vat="Applicable"
        elif re.search(r"VAT\s+(?:is\s+)?not\s+applicable|not\s+subject\s+to\s+VAT",text,re.I):
            vat="Not applicable"
        else:
            vat="UNKNOWN"

        epc=None
        em=re.search(r"\bEPC\b(.{0,260})",text,re.I)
        if em:
            bands=[]
            for b in re.findall(r"\bBand\s+([A-G])\b",em.group(1),re.I):
                b=b.upper()
                if b not in bands: bands.append(b)
            if bands: epc=" / ".join(bands)

        area_sqm=area_sqft=None
        am=re.search(r"(?:total\s+floor\s+area\s+of\s+)?(?:approximately|approx\.?)?\s*([\d,]+(?:\.\d+)?)\s*sq\.?\s*m\.?\s*\(([\d,]+(?:\.\d+)?)\s*sq\.?\s*ft\.?\)",text,re.I)
        if am:
            area_sqm=float(am.group(1).replace(",",""))
            area_sqft=float(am.group(2).replace(",",""))

        pid_match=re.search(r"/property/(\d+)/?",url)
        pid=pid_match.group(1) if pid_match else None
        image=None
        candidates=[]
        for img in soup.find_all("img"):
            src=img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if not src: continue
            u=urljoin(url,src)
            lu=u.lower()
            if pid and re.search(rf"/uploads/\d+-{re.escape(pid)}/",lu):
                score=0
                if "1600x900" in lu: score+=100
                if "800x450" in lu: score+=60
                if "128x72" in lu: score-=80
                candidates.append((score,u))
        if candidates:
            candidates.sort(key=lambda x:(-x[0],len(x[1])))
            image=candidates[0][1]

        row=dict(source="Acuitus",lot=lot,date="2026-09-17",address=address,
                 guide=guide,rent=rent,tenure=tenure,vat=vat,url=url,
                 desc=text[:6500],image=image)
        if guide_status: row["guide_status"]=guide_status
        if epc: row["epc"]=epc
        if area_sqft: row["area_sqft"]=area_sqft
        if area_sqm: row["area_sqm"]=area_sqm
        row["yield"]=100*rent/guide if rent and guide else None
        return row
    except Exception:
        return None


def _acuitus_current():
    url="https://www.acuitus.co.uk/find-a-property/?clear=y"
    try:
        soup=BeautifulSoup(fetch(url),"lxml"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(url,a["href"])
            if re.fullmatch(r"https://(?:www\.)?acuitus\.co\.uk/property/\d+/?",href,re.I) and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_acuitus_exact_row,u) for u in links[:80]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []
'''

if old not in s:
    raise SystemExit('Acuitus collector anchor not found')
s = s.replace(old, new, 1)

# V6.54 later redefines _acuitus_current. Patch that final override too, otherwise
# Python silently replaces the new exact-page collector with the old generic parser.
final_old = '''def _acuitus_current():
    listing='https://www.acuitus.co.uk/find-a-property/?clear=y'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml'); links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if re.search(r'https?://(?:www\\.)?acuitus\\.co\\.uk/property/\\d+/?$',href,re.I) and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v654_exact_row,u,'Acuitus','2026-09-17') for u in links[:40]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []
'''
final_new = '''def _acuitus_current():
    listing='https://www.acuitus.co.uk/find-a-property/?clear=y'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml'); links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if re.fullmatch(r'https?://(?:www\\.)?acuitus\\.co\\.uk/property/\\d+/?',href,re.I) and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_acuitus_exact_row,u) for u in links[:80]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []
'''
if final_old not in s:
    raise SystemExit('Final V6.54 Acuitus override anchor not found')
s = s.replace(final_old, final_new, 1)

old_epc = '''    if p.get("epc"):
        f["EPC"]=str(p["epc"])
'''
new_epc = '''    if p.get("epc"):
        f["EPC"]=str(p["epc"])
        chips.append("EPC "+str(p["epc"]))
'''
if old_epc not in s:
    raise SystemExit('EPC display anchor not found')
s = s.replace(old_epc, new_epc, 1)
APP.write_text(s, encoding='utf-8')

# Load only the non-UI portion and refresh Acuitus, leaving every other source untouched.
marker='rows,health,updated=load_rows()'
ns={'__name__':'acuitus_repair'}
exec(compile(s.split(marker,1)[0], 'app.py', 'exec'), ns)
live=ns['_acuitus_current']()
print('LIVE_ACUITUS', len(live))
if len(live) < 20:
    raise SystemExit('Acuitus collector unexpectedly small; refusing snapshot replacement')

for i, row in enumerate(live):
    if row.get('image'):
        local=ns['_v657_local_image']('Acuitus', row.get('url') or '', row['image'])
        if local:
            row['image']=local
    live[i]=ns['_normalise_rent_semantics'](row)

cache=Path('auction_sniper_cache.json')
payload=json.loads(cache.read_text(encoding='utf-8'))
others=[r for r in payload.get('properties',[]) if r.get('source')!='Acuitus']
payload['properties']=ns['_clean_rows'](others+live)
if len(payload['properties']) < 150:
    raise SystemExit('Refusing shrunken snapshot')
cache.write_text(json.dumps(payload,indent=2),encoding='utf-8')
print('SNAPSHOT_TOTAL', len(payload['properties']))

def find(term):
    return next(r for r in payload['properties'] if r.get('source')=='Acuitus' and term.lower() in (r.get('address') or '').lower())

stone=find('Stonehills')
wilko=find('Fawcett')
print('STONEHILLS',json.dumps(stone,ensure_ascii=False,indent=2)[:6000])
print('WILKO',json.dumps(wilko,ensure_ascii=False,indent=2)[:6000])
assert stone.get('guide') is None, stone.get('guide')
assert stone.get('guide_status')=='Refer to Auctioneer'
assert stone.get('epc')=='E', stone.get('epc')
assert stone.get('vat')=='Not elected', stone.get('vat')
assert abs(stone.get('area_sqft',0)-4534)<1
assert abs(stone.get('area_sqm',0)-421.20)<0.1
assert stone.get('image') and 'app/static/property_images/' in stone['image']
assert wilko.get('epc')=='D', wilko.get('epc')
assert wilko.get('vat')=='Applicable', wilko.get('vat')
assert abs(wilko.get('area_sqft',0)-110154)<1
assert wilko.get('image') and 'app/static/property_images/' in wilko['image']
