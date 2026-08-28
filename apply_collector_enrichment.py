from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

old='from bs4 import BeautifulSoup\n'
new='from bs4 import BeautifulSoup\nfrom collector_enrichment import extract_particulars, merge_enrichment\n'
if new not in s:
    assert old in s
    s=s.replace(old,new,1)

old='''    low=text.lower()\n    return dict(\n        source=source,lot=lot,date=date,address=address,guide=guide,\n        rent=parse_rent(text),\n        tenure=("Freehold" if "freehold" in low[:1800]\n                else "Leasehold" if "leasehold" in low[:1800] else None),\n        vat="UNKNOWN",url=url,desc=text[:1000],image=image\n    )\n'''
new='''    low=text.lower()\n    row=dict(\n        source=source,lot=lot,date=date,address=address,guide=guide,\n        rent=parse_rent(text),\n        tenure=("Freehold" if "freehold" in low[:1800]\n                else "Leasehold" if "leasehold" in low[:1800] else None),\n        vat="UNKNOWN",url=url,desc=text[:1000],image=image\n    )\n    return merge_enrichment(row,extract_particulars(page_html,source,url))\n'''
if old in s:s=s.replace(old,new,1)

old='''    fill_fields=("image","area_sqft","area_sqm","tenant","lease_expiry","break_clause",\n                 "legal_pack","epc","rateable_value","service_charge","ground_rent")\n'''
new='''    fill_fields=("image","area_sqft","area_sqm","tenant","lease_term","lease_start",\n                 "lease_expiry","break_clause","rent_review","erv","fri","legal_pack",\n                 "epc","rateable_value","service_charge","ground_rent")\n'''
if old in s:s=s.replace(old,new,1)

needle='''        if len(rows)<8:\n            raise ValueError("AHL catalogue parse too small")\n        return list(rows.values())\n'''
replacement='''        if len(rows)<8:\n            raise ValueError("AHL catalogue parse too small")\n        def enrich_ahl(item):\n            lotno,row=item\n            try:\n                page_html=fetch(row["url"])\n                return lotno,merge_enrichment(row,extract_particulars(page_html,"Auction House London",row["url"]))\n            except Exception:\n                return lotno,row\n        enriched={}\n        with ThreadPoolExecutor(max_workers=8) as ex:\n            futures=[ex.submit(enrich_ahl,item) for item in rows.items()]\n            for f in as_completed(futures):\n                lotno,row=f.result(); enriched[lotno]=row\n        return list(enriched.values())\n'''
if needle in s:s=s.replace(needle,replacement,1)

marker='''def _merge_catalogue_rows(base_rows):\n'''
if 'def _enrich_exact_rows(rows, source_name' not in s:
    helper='''def _enrich_exact_rows(rows, source_name, limit=220):\n    out=[dict(r) for r in (rows or [])]\n    targets=[i for i,r in enumerate(out) if r.get("url")][:limit]\n    def one(i):\n        r=out[i]\n        try:\n            facts=extract_particulars(fetch(r["url"]),source_name,r["url"])\n            return i,merge_enrichment(r,facts)\n        except Exception:\n            return i,r\n    with ThreadPoolExecutor(max_workers=8) as ex:\n        futures=[ex.submit(one,i) for i in targets]\n        for f in as_completed(futures):\n            i,r=f.result(); out[i]=r\n    return out\n\n'''+marker
    assert marker in s
    s=s.replace(marker,helper,1)

old='''        if rows:\n            if source=="Auction House Regional":\n'''
new='''        if rows:\n            if source=="Bond Wolfe":\n                rows=_enrich_exact_rows(rows,"Bond Wolfe")\n            if source=="Auction House Regional":\n'''
if old in s:s=s.replace(old,new,1)

s=s.replace('BUILD = "V6.63-LEGAL-PACK-INTELLIGENCE"','BUILD = "V6.64-RICH-COLLECTOR-ENRICHMENT"',1)
p.write_text(s,encoding='utf-8')
# workflow trigger 2026-08-28
