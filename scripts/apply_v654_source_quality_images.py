from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.53-PRIORITY-SOURCE-BOOT"','BUILD = "V6.54-SOURCE-QUALITY-IMAGES"',1)

anchor='\ndef refresh_market():\n'
if anchor not in s: raise SystemExit('refresh anchor missing')
insert=r'''

# V6.54 source-specific collectors override the broader V6.52 versions.
def _v652_hero(url, source=""):
    if not url:
        return None
    try:
        raw=fetch(url)
        soup=BeautifulSoup(raw,"lxml")
        src=(source or "").lower()
        candidates=[]

        def add(v):
            if not v: return
            v=html.unescape(str(v)).replace('\\/','/')
            v=urljoin(url,v)
            if v not in candidates: candidates.append(v)

        # Source-specific high confidence first.
        if "clive emson" in src:
            for img in soup.find_all("img"):
                alt=norm(img.get("alt") or "")
                if re.search(r"\bLot\s*:\s*\d+|External image|Internal image",alt,re.I):
                    for a in ("data-src","data-lazy-src","data-original","src"):
                        add(img.get(a))
                    ss=img.get("srcset") or img.get("data-srcset")
                    if ss:
                        for part in ss.split(','): add(part.strip().split(' ')[0])
        elif "acuitus" in src:
            h1=norm(soup.find('h1').get_text(' ',strip=True)) if soup.find('h1') else ''
            for img in soup.find_all('img'):
                alt=norm(img.get('alt') or '')
                if h1 and (alt.lower() in h1.lower() or h1.lower() in alt.lower()):
                    for a in ("data-src","data-lazy-src","data-original","src"): add(img.get(a))
                elif re.search(r"property|auction|building|street|road|house|park",alt,re.I):
                    for a in ("data-src","data-lazy-src","data-original","src"): add(img.get(a))
        elif "strettons" in src:
            decoded=html.unescape(raw).replace('\\/','/')
            for m in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',decoded,re.I):
                add(m)

        # Standard metadata / lazy images.
        for sel,attr in [('meta[property="og:image"]','content'),('meta[name="twitter:image"]','content'),('meta[property="twitter:image"]','content')]:
            t=soup.select_one(sel)
            if t: add(t.get(attr))
        for img in soup.find_all('img'):
            for a in ("data-src","data-lazy-src","data-original","data-image","src"): add(img.get(a))
            ss=img.get('srcset') or img.get('data-srcset')
            if ss:
                for part in ss.split(','): add(part.strip().split(' ')[0])
        for tag in soup.find_all(style=True):
            for m in re.findall(r'url\(["\']?([^"\')]+)',tag.get('style') or '',re.I): add(m)

        filtered=[]
        for c in candidates:
            lc=c.lower()
            if not re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)',lc):
                continue
            if any(x in lc for x in ('logo','favicon','avatar','staff','agent','icon','sprite','placeholder','no-image','noimage','sorry','award','ombudsman','rics','zoopla','onthemarket','social')):
                continue
            if c not in filtered: filtered.append(c)

        if "strettons" in src:
            filtered.sort(key=lambda u:(0 if 'amazonaws.com/i/api_sources/' in u.lower() else 1,0 if '_web_' in u.lower() else 1,len(u)))
        elif "acuitus" in src:
            filtered.sort(key=lambda u:(0 if '/uploads/' in u.lower() or '/images/' in u.lower() else 1,len(u)))
        elif "clive emson" in src:
            filtered.sort(key=lambda u:(0 if any(x in u.lower() for x in ('property','lot','gallery')) else 1,len(u)))
        return filtered[0] if filtered else None
    except Exception:
        return None


def _v654_data_image(image_url, referer=None):
    if not image_url: return None
    if str(image_url).startswith('data:image/'): return image_url
    try:
        h=dict(HEADERS)
        h['Accept']='image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
        if referer: h['Referer']=referer
        r=requests.get(image_url,headers=h,timeout=12,allow_redirects=True)
        ct=(r.headers.get('content-type') or '').split(';')[0].lower()
        if r.ok and ct.startswith('image/') and 800 < len(r.content) < 2500000:
            return f'data:{ct};base64,'+base64.b64encode(r.content).decode('ascii')
    except Exception:
        pass
    return None


def _v654_exact_row(url, source, date=None):
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,'lxml'); text=norm(soup.get_text(' ',strip=True))
        src=source.lower()
        lot='Lot TBC'; address=''; guide=None; rent=None; tenure=None
        if source=='Clive Emson':
            if not re.search(r'/properties/\d+/\d+/?$',url): return None
            h1=norm(soup.find('h1').get_text(' ',strip=True)) if soup.find('h1') else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',h1,re.I)
            if not lm: return None
            lot='Lot '+lm.group(1).upper()
            # Clive's address is the first postcode-bearing H2 on the lot page.
            for h in soup.find_all(['h2','h3']):
                t=norm(h.get_text(' ',strip=True))
                if re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',t,re.I):
                    address=t; break
            if not address:
                address=re.sub(r'^Lot\s*\d+\s*','',h1,flags=re.I).strip()
        elif source=='Acuitus':
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',text,re.I)
            if lm: lot='Lot '+lm.group(1).upper()
        elif source=='Strettons':
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''
            lm=re.search(r'\bLot\s*(\d+[A-Z]?)\b',text,re.I)
            if lm: lot='Lot '+lm.group(1).upper()
        else:
            h1=soup.find('h1'); address=norm(h1.get_text(' ',strip=True)) if h1 else ''

        gm=re.search(r'(?:Guide(?:\s+Price)?\*?|AVAILABLE AT)\s*£?\s*([\d,]+)',text,re.I)
        if gm: guide=float(gm.group(1).replace(',',''))
        rm=re.search(r'(?:Currently\s+let\s+at|Rent|producing|rental income|let at|at a rent of)\s*£?\s*([\d,]+)\s*(?:p\.?a\.?|per annum|pa)',text,re.I)
        if rm: rent=float(rm.group(1).replace(',',''))
        tenure='Freehold' if re.search(r'\bFreehold\b',text,re.I) else 'Leasehold' if re.search(r'\bLeasehold\b',text,re.I) else None
        img=_v652_hero(url,source)
        if img:
            proxied=_v654_data_image(img,url)
            if proxied: img=proxied
        return dict(source=source,lot=lot,date=date,address=address or 'Property',guide=guide,rent=rent,tenure=tenure,vat='UNKNOWN',url=url,desc=text[:1000],image=img)
    except Exception:
        return None


def _clive_emson_current():
    listing='https://www.cliveemson.co.uk/properties/commerical-property-auctions'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml')
        links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            # Genuine lot URLs are exactly /properties/<auction>/<lot>/.
            if re.search(r'https?://(?:www\.)?cliveemson\.co\.uk/properties/\d+/\d+/?$',href,re.I) and href not in links:
                links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs=[ex.submit(_v654_exact_row,u,'Clive Emson',None) for u in links[:80]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _strettons_current():
    listing='https://www.strettons.co.uk/auction-commercial-property/for-sale/'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml'); links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if '/auction-commercial-property-for-sale/' in href and href not in links: links.append(href)
        rows=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs=[ex.submit(_v654_exact_row,u,'Strettons','2026-09-10') for u in links[:50]]
            for f in as_completed(futs):
                r=f.result()
                if r: rows.append(r)
        return _clean_rows(rows)
    except Exception:
        return []


def _acuitus_current():
    listing='https://www.acuitus.co.uk/find-a-property/?clear=y'
    try:
        soup=BeautifulSoup(fetch(listing),'lxml'); links=[]
        for a in soup.find_all('a',href=True):
            href=urljoin(listing,a['href']).split('#')[0]
            if re.search(r'https?://(?:www\.)?acuitus\.co\.uk/property/\d+/?$',href,re.I) and href not in links: links.append(href)
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
s=s.replace(anchor,insert+anchor,1)

# Version the priority boot cache so previous contaminated Clive data cannot survive.
old='''@st.cache_data(ttl=21600,show_spinner=False)
def _v653_priority_boot_rows():'''
new='''@st.cache_data(ttl=1800,show_spinner=False)
def _v654_priority_boot_rows():'''
if old in s: s=s.replace(old,new,1)
s=s.replace('priority=_v653_priority_boot_rows()','priority=_v654_priority_boot_rows()',1)

# Remove any already-cached Clive navigation pages, then refresh images for priority rows.
needle='''    if priority:
        rows=_merge_property_universe(rows,priority)
except Exception:
    pass
st.markdown('''
replacement='''    if priority:
        rows=_merge_property_universe(rows,priority)
    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\\d+/\\d+/?$",r.get("url") or "",re.I)]
    for i,r in enumerate(rows):
        if r.get("source") in ("Strettons","Acuitus","Clive Emson") and (not r.get("image") or not str(r.get("image")).startswith("data:image/")):
            img=_v652_hero(r.get("url") or "",r.get("source") or "")
            if img:
                proxied=_v654_data_image(img,r.get("url") or "")
                if proxied: rows[i]["image"]=proxied
except Exception:
    pass
st.markdown('''
if needle not in s: raise SystemExit('priority boot merge anchor missing')
s=s.replace(needle,replacement,1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.54 source quality and image extraction applied')
