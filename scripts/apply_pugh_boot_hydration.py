from pathlib import Path
import py_compile

p=Path('app.py')
c=p.read_text(encoding='utf-8')

anchor='''def _apply_seed_image_map(rows):
    out=[]
    for row in rows:
        r=dict(row)
        if not r.get("image") and r.get("url") in VERIFIED_SEED_IMAGES:
            r["image"]=VERIFIED_SEED_IMAGES[r["url"]]
        if r.get("source")=="Savills Auctions":
            try:
                r=_apply_verified_savills_current(r)
            except Exception:
                pass
        out.append(r)
    return out
'''
addition=anchor+'''\n@st.cache_data(ttl=21600, show_spinner=False)
def _pugh_seed_exact_rows(targets):
    """Hydrate only the known Pugh/BTG commercial seed lots from exact pages.

    This avoids crawling every residential lot at startup while ensuring that
    the verified Pugh/BTG cards do not boot with generic catalogue URLs and no images.
    """
    catalogue="https://www.btgeddisonspropertyauctions.com/auctions/live-stream/august-2026?auction_id=17&date_added=0&limit=0&radius=1&search_type=auction&view=grid"
    try:
        s=BeautifulSoup(fetch(catalogue),"lxml")
        wanted=[]
        for lot,address in targets:
            addr=norm(address).lower()
            best=None
            for a in s.find_all("a",href=True):
                href=urljoin(catalogue,a["href"])
                if "/properties/" not in href:
                    continue
                label=norm(a.get_text(" ",strip=True)).lower()
                if label and (label==addr or label in addr or addr in label):
                    best=href
                    break
            if best:
                wanted.append((lot,best))

        hydrated=[]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures={ex.submit(_exact_page_card,u,"Pugh / BTG Eddisons","2026-08-27",True):(lot,u) for lot,u in wanted}
            for f in as_completed(futures):
                lot,u=futures[f]
                try:
                    r=f.result()
                    if r:
                        r["lot"]=lot
                        r["url"]=u
                        hydrated.append(r)
                except Exception:
                    pass
        return hydrated
    except Exception:
        return []

def _hydrate_pugh_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Pugh / BTG Eddisons" and (not r.get("image") or "/auctions/live-stream/" in (r.get("url") or "") or "pugh-auctions.com/property/" in (r.get("url") or ""))]
    if not missing:
        return rows
    targets=tuple((r.get("lot") or "Lot TBC",r.get("address") or "") for r in missing if r.get("address"))
    live=_pugh_seed_exact_rows(targets)
    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
assert anchor in c, 'seed image anchor changed'
c=c.replace(anchor,addition,1)

old='''    rows=_merge_property_universe(SEED,cached_rows)
    rows=_apply_seed_image_map(rows)
    return rows,health,updated
'''
new='''    rows=_merge_property_universe(SEED,cached_rows)
    rows=_apply_seed_image_map(rows)
    # Pugh/BTG seed records historically used a generic catalogue URL, so no
    # property image could render until a manual full refresh. Hydrate just the
    # known commercial Pugh/BTG cards from their exact current lot pages.
    rows=_hydrate_pugh_seed_rows(rows)
    return rows,health,updated
'''
assert old in c, 'load_rows anchor changed'
c=c.replace(old,new,1)
c=c.replace('BUILD = "V6.20-BTG-GALLERY"','BUILD = "V6.21-BTG-BOOT"',1)
p.write_text(c,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
assert '_hydrate_pugh_seed_rows(rows)' in c
assert 'Pugh/BTG seed records historically used a generic catalogue URL' in c
print('Pugh/BTG boot hydration patch passed')
