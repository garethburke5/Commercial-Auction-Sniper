from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

s=s.replace('BUILD = "V6.27-COMPACT-PRODUCTION"','BUILD = "V6.28-IMAGE-REPAIR"',1)

old='''                imgs=_img_candidates(s,href)
                image=None
                for cand in imgs:
                    lc=cand.lower()
                    if any(x in lc for x in ("logo","agent","staff","avatar","icon")):
                        continue
                    image=cand
                    break
'''
new='''                # Strettons: choose the image from the exact property page, not
                # the catalogue card. This catches lazy/srcset/OG gallery images.
                image=_property_image_from_soup(s,href)
                if not image:
                    imgs=_img_candidates(s,href)
                    for cand in imgs:
                        lc=cand.lower()
                        if any(x in lc for x in ("logo","agent","staff","avatar","icon","social")):
                            continue
                        image=cand
                        break
'''
if old not in s:
    raise SystemExit('Strettons image anchor not found')
s=s.replace(old,new,1)

old='''            href=urljoin(url,a["href"])
            if href in seen: continue
            gm=re.search(r"Guide\\*?\\s*(£[\\d,]+)",card,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            ym=re.search(r"Yield[^0-9]*([\\d.]+)%",card,re.I)
            y=float(ym.group(1)) if ym else None
            rent=(guide*y/100) if guide and y else None
            address=norm(a.get_text(" ",strip=True)) or card[:180]
            imgs=_img_candidates(node,url) if "_img_candidates" in globals() else []
            rows.append(dict(source="Acuitus",lot="Lot TBC",date="2026-09-17",
                             address=address,guide=guide,rent=rent,tenure=None,
                             vat="UNKNOWN",url=href,desc=card[:350],
                             image=imgs[0] if imgs else None))
            seen.add(href)
'''
new='''            href=urljoin(url,a["href"])
            # Acuitus property detail pages use /property/<id>/. Catalogue and
            # navigation links do not carry a reliable hero image.
            if "/property/" not in href.lower() or href in seen:
                continue
            gm=re.search(r"Guide\\*?\\s*(£[\\d,]+)",card,re.I)
            guide=parse_money(gm.group(1)) if gm else None
            ym=re.search(r"Yield[^0-9]*([\\d.]+)%",card,re.I)
            y=float(ym.group(1)) if ym else None
            rent=(guide*y/100) if guide and y else None
            address=norm(a.get_text(" ",strip=True)) or card[:180]
            image=None
            try:
                ds=BeautifulSoup(fetch(href),"lxml")
                h=ds.find("h1")
                if h:
                    exact_address=norm(h.get_text(" ",strip=True))
                    if exact_address:
                        address=exact_address
                image=_property_image_from_soup(ds,href)
            except Exception:
                pass
            rows.append(dict(source="Acuitus",lot="Lot TBC",date="2026-09-17",
                             address=address,guide=guide,rent=rent,tenure=None,
                             vat="UNKNOWN",url=href,desc=card[:350],image=image))
            seen.add(href)
'''
if old not in s:
    raise SystemExit('Acuitus image anchor not found')
s=s.replace(old,new,1)

anchor='''def _hydrate_strettons_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Strettons" and (not r.get("image") or "/auction-commercial-property/for-sale" in (r.get("url") or ""))]
    if not missing:
        return rows
    live=_strettons_seed_exact_rows(tuple(r.get("lot") for r in missing if r.get("lot")))
    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
insert=anchor+'''

def _hydrate_acuitus_images(rows):
    """Hydrate missing Acuitus previews from exact /property/<id>/ pages."""
    out=[dict(r) for r in rows]
    targets=[i for i,r in enumerate(out) if r.get("source")=="Acuitus" and not r.get("image") and "/property/" in (r.get("url") or "").lower()]
    if not targets:
        return out
    def one(i):
        try:
            u=out[i].get("url")
            ds=BeautifulSoup(fetch(u),"lxml")
            return i,_property_image_from_soup(ds,u)
        except Exception:
            return i,None
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[ex.submit(one,i) for i in targets]
        for f in as_completed(futs):
            i,img=f.result()
            if img:
                out[i]["image"]=img
    return out
'''
if anchor not in s:
    raise SystemExit('Strettons hydrate anchor not found')
s=s.replace(anchor,insert,1)

old='''    rows=_hydrate_strettons_seed_rows(rows)
    return rows,health,updated
'''
new='''    rows=_hydrate_strettons_seed_rows(rows)
    rows=_hydrate_acuitus_images(rows)
    return rows,health,updated
'''
if old not in s:
    raise SystemExit('load_rows image hydration anchor not found')
s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.28 Acuitus/Strettons image repair applied')
