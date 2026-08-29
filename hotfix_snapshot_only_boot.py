from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.69-ACUITUS-STRUCTURED"','BUILD = "V6.70-SNAPSHOT-FAST-BOOT"',1)
old='''rows,health,updated=load_rows()\ntry:\n    priority=_v654_priority_boot_rows()\n    if priority:\n        rows=_merge_property_universe(rows,priority)\n    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\\d+/\\d+/?$",r.get("url") or "",re.I)]\n    rows=_v657_localise_priority_rows(rows)\n    rows=[_normalise_rent_semantics(r) for r in rows]\nexcept Exception:\n    pass\n'''
new='''rows,health,updated=load_rows()\n# Production startup must be snapshot-only. Live auction-site scraping is handled by\n# the scheduled collector workflow and the explicit Update listings action, never\n# during first render. This keeps Streamlit boot deterministic and fast.\ntry:\n    rows=[r for r in rows if r.get("source")!="Clive Emson" or re.search(r"/properties/\\d+/\\d+/?$",r.get("url") or "",re.I)]\n    rows=_v657_localise_priority_rows(rows)\n    rows=[_normalise_rent_semantics(r) for r in rows]\nexcept Exception:\n    pass\n'''
if old not in s:
    raise SystemExit('startup live-scrape block not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
