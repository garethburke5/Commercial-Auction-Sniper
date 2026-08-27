from pathlib import Path
import py_compile

p=Path('app.py')
c=p.read_text(encoding='utf-8')

old='''def _hydrate_pugh_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Pugh / BTG Eddisons" and (not r.get("image") or "/auctions/live-stream/" in (r.get("url") or "") or "pugh-auctions.com/property/" in (r.get("url") or ""))]
    if not missing:
        return rows
    targets=tuple((r.get("lot") or "Lot TBC",r.get("address") or "") for r in missing if r.get("address"))
    live=_pugh_seed_exact_rows(targets)
    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
new='''def _hydrate_pugh_seed_rows(rows):
    missing=[r for r in rows if r.get("source")=="Pugh / BTG Eddisons" and (not r.get("image") or "/auctions/live-stream/" in (r.get("url") or "") or "pugh-auctions.com/property/" in (r.get("url") or ""))]
    if not missing:
        return rows

    # Never rediscover an exact current BTG URL we already know. Percy Street is
    # a useful example: its catalogue card has partner-agent markup around the
    # link, but the exact property URL itself is stable and fully verifiable.
    direct=[]
    discover=[]
    for r in missing:
        u=r.get("url") or ""
        if "btgeddisonspropertyauctions.com/properties/" in u:
            direct.append((r.get("lot") or "Lot TBC",u))
        elif r.get("address"):
            discover.append((r.get("lot") or "Lot TBC",r.get("address") or ""))

    live=[]
    if direct:
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures={ex.submit(_exact_page_card,u,"Pugh / BTG Eddisons","2026-08-27",True):(lot,u) for lot,u in direct}
            for f in as_completed(futures):
                lot,u=futures[f]
                try:
                    rec=f.result()
                    if rec:
                        rec["lot"]=lot
                        rec["url"]=u
                        live.append(rec)
                except Exception:
                    pass
    if discover:
        live.extend(_pugh_seed_exact_rows(tuple(discover)))

    if not live:
        return rows
    return _merge_property_universe(rows,live)
'''
assert old in c, 'Pugh hydration function changed'
c=c.replace(old,new,1)
c=c.replace('BUILD = "V6.22-BTG-19OF19"','BUILD = "V6.23-BTG-EXACT-FIRST"',1)
p.write_text(c,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
assert 'Never rediscover an exact current BTG URL' in c
print('Pugh/BTG exact-URL-first hydration patch passed')
