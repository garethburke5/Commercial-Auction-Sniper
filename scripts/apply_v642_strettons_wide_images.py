from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

# Build marker
import re
s=re.sub(r'BUILD = "V6\.[^"]+"','BUILD = "V6.42-STRETTONS-WIDE-IMAGES"',s,count=1)

# Ensure base64 support for server-side Strettons image delivery.
if 'import base64\n' not in s:
    s=s.replace('import re, html, json, time\n','import re, html, json, time\nimport base64\n',1)

# Make exact-page generic parser use the verified Strettons embedded image extractor.
anchor='''        image=None
        candidates=_img_candidates(s,url)

        # BTG/Pugh: host alone is not proof of a property photograph.'''
replacement='''        image=None
        candidates=_img_candidates(s,url)

        # Strettons property photos are embedded in page data rather than ordinary <img> tags.
        # Use the verified api_sources extractor before generic image selection.
        if "strettons.co.uk" in (url or "").lower():
            image=_strettons_exact_image(s,url)

        # BTG/Pugh: host alone is not proof of a property photograph.'''
if anchor not in s:
    raise SystemExit('exact-page image anchor missing')
s=s.replace(anchor,replacement,1)

# Strengthen boot hydration: exact Strettons rows with missing images should be repaired directly,
# not only generic catalogue seed URLs.
old='''def _hydrate_strettons_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Strettons" and (not r.get("image") or "/auction-commercial-property/for-sale" in (r.get("url") or ""))]
    if not missing:
        return rows
    live=_strettons_seed_exact_rows(tuple(r.get("lot") for r in missing if r.get("lot")))
    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
new='''def _hydrate_strettons_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Strettons" and (not r.get("image") or "/auction-commercial-property/for-sale" in (r.get("url") or ""))]
    if not missing:
        return rows

    live=[]
    discover=[]
    direct=[]
    for r in missing:
        u=r.get("url") or ""
        if "/auction-commercial-property-for-sale/" in u:
            direct.append((r.get("lot") or "Lot TBC",u))
        elif r.get("lot"):
            discover.append(r.get("lot"))

    def hydrate_exact(item):
        lot,u=item
        try:
            ds=BeautifulSoup(fetch(u),"lxml")
            img=_strettons_exact_image(ds,u)
            main=ds.find("main") or ds
            text=norm(main.get_text(" ",strip=True))
            h=ds.find("h1")
            address=norm(h.get_text(" ",strip=True)) if h else ""
            gm=re.search(r"Guide Price\\s*£?\\s*([\\d,]+)",text,re.I)
            guide=float(gm.group(1).replace(',','')) if gm else None
            low=text.lower()
            return dict(source="Strettons",lot=lot,date="2026-09-10",address=address,
                        guide=guide,rent=parse_rent(text),
                        tenure=("Freehold" if "freehold" in low[:2200] else "Leasehold" if "leasehold" in low[:2200] else None),
                        vat="UNKNOWN",url=u,desc=text[:1800],image=img)
        except Exception:
            return None

    if direct:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures=[ex.submit(hydrate_exact,x) for x in direct]
            for f in as_completed(futures):
                rec=f.result()
                if rec and rec.get("image"):
                    live.append(rec)
    if discover:
        live.extend(_strettons_seed_exact_rows(tuple(discover)))
    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
if old not in s:
    raise SystemExit('strettons hydrate block missing')
s=s.replace(old,new,1)

# Add a cached server-side data-URI fallback. This bypasses browser hotlink/CORS/referrer behaviour
# while keeping the image clickable to the property page.
insert_before='''def money(v): return "—" if v is None else f"£{v:,.0f}"'''
helper='''@st.cache_data(ttl=21600, show_spinner=False)
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
if insert_before not in s:
    raise SystemExit('money helper anchor missing')
s=s.replace(insert_before,helper+insert_before,1)

# Render through the safe source.
old_preview='''        preview=(f'<a class="previewLink" href="{_property_url}" target="_blank" rel="noopener noreferrer"><img class="preview" src="{html.escape(x["image"],quote=True)}" loading="lazy"></a>' if x.get("image") and _property_url
                 else (f'<img class="preview" src="{html.escape(x["image"],quote=True)}" loading="lazy">' if x.get("image") else '<div class="preview noimg">Photo unavailable</div>'))'''
new_preview='''        _image_src=_safe_card_image_src(x.get("source"),x.get("image"))
        preview=(f'<a class="previewLink" href="{_property_url}" target="_blank" rel="noopener noreferrer"><img class="preview" src="{html.escape(_image_src,quote=True)}" loading="lazy"></a>' if _image_src and _property_url
                 else (f'<img class="preview" src="{html.escape(_image_src,quote=True)}" loading="lazy">' if _image_src else '<div class="preview noimg">Photo unavailable</div>'))'''
if old_preview not in s:
    raise SystemExit('preview render anchor missing')
s=s.replace(old_preview,new_preview,1)

# Force photographs edge-to-edge horizontally and give them modestly more visual weight.
css='''
/* V6.42 wider property photography */
.previewLink{display:block!important;width:100%!important;margin:0!important;padding:0!important;overflow:hidden!important}
.preview{display:block!important;width:100%!important;max-width:none!important;margin:0!important;padding:0!important;height:178px!important;object-fit:cover!important}
@media(min-width:1700px){.preview{height:176px!important}}
@media(max-width:1180px){.preview{height:174px!important}}
@media(max-width:820px){.preview{height:162px!important}}
@media(max-width:650px){.preview{height:122px!important}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.42 applied: Strettons server-side images + wider edge-to-edge previews')
