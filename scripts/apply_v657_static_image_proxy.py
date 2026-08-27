from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.55-FUNCTIONAL-FILTERS"','BUILD = "V6.57-STATIC-IMAGE-PROXY"',1)
if 'import hashlib' not in s:
    s=s.replace('import base64\n','import base64\nimport hashlib\n',1)

anchor='\ndef refresh_market():\n'
if anchor not in s:
    raise SystemExit('refresh_market anchor missing')
insert=r'''

# V6.57: serve troublesome auction-house photos from Auction Sniper itself.
# Direct hotlinks and data: URIs have both proved unreliable in Streamlit Cloud.
STATIC_IMAGE_DIR=Path('static/property_images')
STATIC_IMAGE_DIR.mkdir(parents=True,exist_ok=True)


def _v657_candidate_images(property_url, source):
    if not property_url:
        return []
    try:
        raw=fetch(property_url)
    except Exception:
        return []
    soup=BeautifulSoup(raw,'lxml')
    out=[]
    def add(v):
        if not v: return
        v=html.unescape(str(v)).replace('\\/','/').strip(' "\'')
        if v.startswith('//'): v='https:'+v
        v=urljoin(property_url,v)
        if v not in out: out.append(v)

    # Structured metadata first.
    for sel,attr in [
        ('meta[property="og:image"]','content'),
        ('meta[name="twitter:image"]','content'),
        ('meta[itemprop="image"]','content'),
        ('link[rel="image_src"]','href'),
    ]:
        for tag in soup.select(sel): add(tag.get(attr))

    # Normal/lazy image elements and srcsets.
    for img in soup.find_all('img'):
        for a in ('data-src','data-lazy-src','data-original','data-image','data-large','data-full','src'):
            add(img.get(a))
        for a in ('srcset','data-srcset'):
            ss=img.get(a)
            if ss:
                parts=[x.strip().split(' ')[0] for x in ss.split(',') if x.strip()]
                for u in reversed(parts): add(u)

    # CSS and script/JSON galleries (important for Strettons and Clive Emson).
    decoded=html.unescape(raw).replace('\\/','/')
    for m in re.findall(r'(?:https?:)?//[^"\'<>\\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\\s]*)?',decoded,re.I): add(m)
    for m in re.findall(r'["\']([^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',decoded,re.I): add(m)
    for tag in soup.find_all(style=True):
        for m in re.findall(r'url\(["\']?([^"\')]+)',tag.get('style') or '',re.I): add(m)

    bad=('logo','favicon','avatar','staff','agent','icon','sprite','placeholder','no-image','noimage','sorry','award','ombudsman','rics','zoopla','onthemarket','social','spinner','loading','cookie')
    clean=[]
    for u in out:
        lu=u.lower()
        if not re.search(r'\.(?:jpe?g|png|webp)(?:\?|$)',lu): continue
        if any(x in lu for x in bad): continue
        if u not in clean: clean.append(u)

    src=(source or '').lower()
    def score(u):
        lu=u.lower(); sc=0
        if 'strettons' in src:
            if 'amazonaws.com/i/api_sources/' in lu: sc+=100
            if '_web_' in lu: sc+=70
            if 'property' in lu or 'auction' in lu: sc+=25
        elif 'acuitus' in src:
            if '/uploads/' in lu: sc+=100
            if re.search(r'/\d+-\d+/',lu): sc+=60
            if 'banner' in lu or 'property' in lu: sc+=30
        elif 'clive emson' in src:
            if 'property' in lu or 'properties' in lu: sc+=70
            if 'lot' in lu: sc+=55
            if any(x in lu for x in ('gallery','photo','image')): sc+=30
        # Prefer sizeable originals over tiny thumbnails when filename gives hints.
        if any(x in lu for x in ('160x','100x','thumb','thumbnail')): sc-=20
        return (-sc,len(u))
    clean.sort(key=score)
    return clean


def _v657_local_image(source, property_url, image_url=None):
    if source not in ('Strettons','Acuitus','Clive Emson'):
        return image_url
    candidates=[]
    if image_url and not str(image_url).startswith('data:'):
        candidates.append(str(image_url))
    for u in _v657_candidate_images(property_url,source):
        if u not in candidates: candidates.append(u)
    for u in candidates[:18]:
        try:
            h=dict(HEADERS)
            h.update({'Accept':'image/avif,image/webp,image/apng,image/*,*/*;q=0.8','Referer':property_url or ''})
            r=requests.get(u,headers=h,timeout=15,allow_redirects=True)
            ct=(r.headers.get('content-type') or '').split(';')[0].lower()
            if not r.ok or not ct.startswith('image/') or len(r.content)<2500 or len(r.content)>5000000:
                continue
            # Reject known placeholder artwork by URL and suspiciously tiny dimensions where Pillow is unavailable.
            lu=(r.url or u).lower()
            if any(x in lu for x in ('placeholder','no-image','noimage','sorry')): continue
            ext={
                'image/jpeg':'.jpg','image/jpg':'.jpg','image/png':'.png','image/webp':'.webp','image/gif':'.gif'
            }.get(ct,'.jpg')
            key=hashlib.sha1((source+'|'+property_url+'|'+u).encode('utf-8')).hexdigest()[:20]
            path=STATIC_IMAGE_DIR/(key+ext)
            if not path.exists(): path.write_bytes(r.content)
            return 'app/static/property_images/'+path.name
        except Exception:
            continue
    return None


def _v657_localise_priority_rows(rows):
    targets=[(i,r) for i,r in enumerate(rows) if r.get('source') in ('Strettons','Acuitus','Clive Emson')]
    def one(i,r):
        return i,_v657_local_image(r.get('source'),r.get('url') or '',r.get('image'))
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(one,i,r) for i,r in targets]
        for f in as_completed(futs):
            try:
                i,src=f.result()
                if src: rows[i]['image']=src
            except Exception:
                pass
    return rows
'''
s=s.replace(anchor,insert+anchor,1)

# Run local-image pass after priority-source merge, replacing prior data-URI-only repair.
needle='''    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\\d+/\\d+/?$",r.get("url") or "",re.I)]
    for i,r in enumerate(rows):
        if r.get("source") in ("Strettons","Acuitus","Clive Emson") and (not r.get("image") or not str(r.get("image")).startswith("data:image/")):
            img=_v652_hero(r.get("url") or "",r.get("source") or "")
            if img:
                proxied=_v654_data_image(img,r.get("url") or "")
                if proxied: rows[i]["image"]=proxied
'''
replacement='''    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\\d+/\\d+/?$",r.get("url") or "",re.I)]
    rows=_v657_localise_priority_rows(rows)
'''
if needle not in s:
    raise SystemExit('priority render repair anchor missing')
s=s.replace(needle,replacement,1)

# Make card render use static local files for all three priority sources.
old='''@st.cache_data(ttl=21600, show_spinner=False)
def _safe_card_image_src(source,image_url):
    if not image_url:
        return None
    if (source or "").lower() != "strettons":
        return image_url
    try:
        r=requests.get(image_url,headers={**HEADERS,"Referer":"https://www.strettons.co.uk/"},timeout=15)
        r.raise_for_status()
        ctype=(r.headers.get("content-type") or "image/jpeg").split(";")[0]
        if not ctype.startswith("image/"):
            return image_url
        encoded=base64.b64encode(r.content).decode("ascii")
        return f"data:{ctype};base64,{encoded}"
    except Exception:
        return image_url
'''
new='''def _safe_card_image_src(source,image_url):
    return image_url or None
'''
if old in s:
    s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.57 static image proxy applied')
