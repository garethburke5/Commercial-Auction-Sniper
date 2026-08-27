from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.36-IMAGE-DELIVERY"',s,count=1)

# Auctioneer image hosts can reject direct browser hotlinks even when our server can fetch them.
# Proxy affected images through the Streamlit app as data URIs so cards receive actual bytes.
if 'def _display_image_src(' not in s:
    anchor='def load_rows():'
    helper='''def _display_image_src(image_url, source):
    """Return a browser-safe preview source; proxy hotlink-sensitive auctioneer images."""
    if not image_url:
        return None
    src=(source or "").lower()
    if not any(k in src for k in ("strettons","acuitus")):
        return image_url
    try:
        import base64
        r=requests.get(image_url,headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
            "Referer":"https://www.strettons.co.uk/" if "strettons" in src else "https://www.acuitus.co.uk/",
            "Accept":"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        },timeout=12)
        ctype=(r.headers.get("content-type") or "").split(";")[0].lower()
        if r.ok and ctype.startswith("image/") and len(r.content)>1500:
            return f"data:{ctype};base64,{base64.b64encode(r.content).decode('ascii')}"
    except Exception:
        pass
    return image_url

'''
    if anchor not in s: raise SystemExit('load_rows anchor missing')
    s=s.replace(anchor,helper+anchor,1)

# Acuitus: exact pages visibly expose a gallery; broaden extraction to JSON-LD and raw HTML URLs.
if 'def _acuitus_exact_image(' not in s:
    anchor='def _hydrate_acuitus_images(rows):'
    helper='''def _acuitus_exact_image(soup_obj,page_url):
    candidates=[]
    def add(raw,score=0):
        if not raw: return
        u=urljoin(page_url,html.unescape(str(raw)).replace('\\/','/'))
        low=u.lower()
        if not re.search(r'\\.(?:jpe?g|png|webp)(?:\\?|$)',low): return
        if any(x in low for x in ('logo','icon','sprite','avatar','map','marker','favicon')): return
        if '/property/' in low or 'upload' in low or 'image' in low or 'photo' in low: score+=3
        candidates.append((score,u))
    for meta in soup_obj.find_all('meta'):
        key=(meta.get('property') or meta.get('name') or '').lower()
        if key in ('og:image','twitter:image','twitter:image:src'): add(meta.get('content'),8)
    for tag in soup_obj.find_all(['img','source']):
        for attr in ('src','data-src','data-lazy-src','data-original','srcset','data-srcset'):
            val=tag.get(attr)
            if val:
                for part in str(val).split(','): add(part.strip().split(' ')[0],4)
    raw=str(soup_obj)
    for u in re.findall(r'https?:[^\\"\\\'<> ]+?\\.(?:jpg|jpeg|png|webp)(?:\\?[^\\"\\\'<> ]*)?',raw,re.I): add(u,2)
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0][1] if candidates else None

'''
    if anchor not in s: raise SystemExit('Acuitus hydrate anchor missing')
    s=s.replace(anchor,helper+anchor,1)

# Prefer stronger Acuitus parser in hydration.
s=s.replace('return i,_property_image_from_soup(ds,u)','return i,_acuitus_exact_image(ds,u) or _property_image_from_soup(ds,u)',1)

# Use server-proxied display source for affected cards while preserving original image URL in data.
old='''        _property_url=html.escape(str(x.get("url") or ""),quote=True)'''
new='''        _property_url=html.escape(str(x.get("url") or ""),quote=True)
        _display_image=_display_image_src(x.get("image"),x.get("source"))'''
if old not in s: raise SystemExit('card property url anchor missing')
s=s.replace(old,new,1)
# Replace image rendering expressions only in preview block.
s=s.replace('x.get("image") and _property_url','_display_image and _property_url',1)
s=s.replace('html.escape(x["image"],quote=True)','html.escape(_display_image,quote=True)',2)
s=s.replace('if x.get("image") else','if _display_image else',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.36 resilient Strettons/Acuitus image delivery applied')
