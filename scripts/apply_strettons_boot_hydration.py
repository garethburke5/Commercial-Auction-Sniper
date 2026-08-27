from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

old='''    rows=_hydrate_pugh_seed_rows(rows)\n    return rows,health,updated\n'''
new='''    rows=_hydrate_pugh_seed_rows(rows)\n    # Strettons seed rows also begin with the generic commercial catalogue URL.\n    # Resolve the current lot cards to exact property pages at boot so preview\n    # images and exact navigation work before a manual full refresh.\n    rows=_hydrate_strettons_seed_rows(rows)\n    return rows,health,updated\n'''
if old not in s:
    raise SystemExit('load_rows insertion point not found')
s=s.replace(old,new,1)

marker='''def load_rows():\n'''
fn='''@st.cache_data(ttl=21600, show_spinner=False)\ndef _strettons_seed_exact_rows(target_lots):\n    \"\"\"Resolve known Strettons seed lots to exact current property pages.\"\"\"\n    listing=\"https://www.strettons.co.uk/auction-commercial-property/for-sale/\"\n    wanted=set(target_lots)\n    if not wanted:\n        return []\n    try:\n        soup=BeautifulSoup(fetch(listing),\"lxml\")\n        links={}\n        for a in soup.find_all(\"a\",href=True):\n            href=urljoin(listing,a[\"href\"])\n            if \"/auction-commercial-property-for-sale/\" not in href:\n                continue\n            node=a; card=\"\"\n            for _ in range(9):\n                node=getattr(node,\"parent\",None)\n                if node is None: break\n                t=norm(node.get_text(\" \",strip=True))\n                if re.search(r\"10 Sep 26\\s*-\\s*Lot\\s+\\d+\",t,re.I) and len(t)<5000:\n                    card=t; break\n            if not card: continue\n            m=re.search(r\"10 Sep 26\\s*-\\s*Lot\\s+(\\d+[A-Z]?)\",card,re.I)\n            if not m: continue\n            lot=\"Lot \"+m.group(1)\n            if lot in wanted:\n                links[lot]=href\n\n        live=[]\n        with ThreadPoolExecutor(max_workers=8) as ex:\n            futures={ex.submit(_exact_page_card,u,\"Strettons\",\"2026-09-10\",True):(lot,u) for lot,u in links.items()}\n            for f in as_completed(futures):\n                lot,u=futures[f]\n                try:\n                    rec=f.result()\n                    if rec:\n                        rec[\"lot\"]=lot\n                        rec[\"url\"]=u\n                        live.append(rec)\n                except Exception:\n                    pass\n        return live\n    except Exception:\n        return []\n\ndef _hydrate_strettons_seed_rows(rows):\n    missing=[r for r in rows if r.get(\"source\")==\"Strettons\" and (not r.get(\"image\") or \"/auction-commercial-property/for-sale\" in (r.get(\"url\") or \"\"))]\n    if not missing:\n        return rows\n    live=_strettons_seed_exact_rows(tuple(r.get(\"lot\") for r in missing if r.get(\"lot\")))\n    if not live:\n        return rows\n    return _merge_property_universe(rows,live)\n\n'''
if marker not in s:
    raise SystemExit('load_rows marker not found')
s=s.replace(marker,fn+marker,1)
s=s.replace('BUILD = "V6.23-BTG-EXACT-FIRST"','BUILD = "V6.24-STRETTONS-EXACT-BOOT"',1)
p.write_text(s,encoding='utf-8')
