from pathlib import Path
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

from collectors.core import Lot, SourceResult, clean_description
from collectors.utils import enrich_common_fields
from collectors.auction_house_london_v2 import collect as ahl
from collectors.auction_house_regions import (
    collect_east_anglia, collect_west_yorkshire, collect_sussex_hampshire,
    collect_south_west, collect_wales, collect_cumbria, collect_north_east, collect_north_west,
    collect_lincolnshire, collect_manchester, collect_chesterfield, collect_coventry_warwickshire,
    collect_scotland, collect_hull_east_yorkshire, collect_birmingham_black_country,
    collect_northants_beds_bucks, collect_beds_bucks, collect_leicestershire, collect_tees_valley,
    collect_national_online,
)
from collectors.savills_all_future import collect as savills
from collectors.bond_wolfe_v2 import collect as bond_wolfe
from collectors.pugh import collect as pugh
from collectors.strettons import collect as strettons
from collectors.lsh import collect as lsh
from collectors.acuitus import collect as acuitus
from collectors.pattinson_resilient import collect as pattinson
from collectors.mchugh import collect as mchugh
from collectors.clive_emson import collect as clive_emson
from collectors.allsop import collect as allsop
from collectors.barnard_marcus import collect as barnard_marcus
from collectors.barnett_ross import collect as barnett_ross
from collectors.harman_healy import collect as harman_healy
from collectors.knight_frank import collect as knight_frank
from collectors.town_country import collect as town_country
from collectors.future_property_auctions import collect as future_property
from collectors.bidx1 import collect as bidx1
from collectors.symonds_sampson import collect as symonds_sampson
from collectors.auction_estates import collect as auction_estates
from source_manifest import append_missing_health, manifest_coverage

DATA=Path("data")
DATA.mkdir(exist_ok=True)
COLLECTORS=[
    ahl,
    collect_east_anglia, collect_west_yorkshire, collect_sussex_hampshire,
    collect_south_west, collect_wales, collect_cumbria, collect_north_east, collect_north_west,
    collect_lincolnshire, collect_manchester, collect_chesterfield, collect_coventry_warwickshire,
    collect_scotland, collect_hull_east_yorkshire, collect_birmingham_black_country,
    collect_northants_beds_bucks, collect_beds_bucks, collect_leicestershire, collect_tees_valley,
    collect_national_online,
    savills, bond_wolfe, pugh, strettons, lsh, pattinson, mchugh, allsop, acuitus,
    clive_emson, barnard_marcus, barnett_ross, harman_healy, knight_frank, town_country,
    future_property, bidx1, symonds_sampson, auction_estates,
]
PUBLISHABLE={"LIVE","DEGRADED"}
TERMINAL_STATUSES={"SOLD PRIOR","WITHDRAWN","WITHDRAWN PRIOR","POSTPONED","AUCTION ENDED","COMPLETED","ARCHIVED"}
BAD_ADDRESS=re.compile(r"(?:login|log in|sign in|register to bid|book a viewing|arrange a viewing|viewing appointment|cancel proxy bid|your bid|remove from wishlist|add to wishlist|connecting to auction|please wait|full details|legal pack available)",re.I)
DESCRIPTION_BOILERPLATE=re.compile(r"(?:book your free appraisal|register to bid|create account\s*/\s*login|my account|auction countdown|book a viewing|sign up for auction alerts)",re.I)
RICH_FIELDS=("image_url","area_sqft","area_sqm","site_area_acres","tenant","lease_term","lease_start","lease_expiry","break_clause","break_status","rent_review","fri","erv","epc","rateable_value","service_charge","ground_rent","property_type","occupation","parking","development_potential","asset_management","refurbishment","residential_conversion","listed_status","covenant_rating","covenant_risk","covenant_turnover","guarantors","pitch","nearby_occupiers","legal_pack_url","legal_pack_status","vat_status","tenure","guide_price","annual_rent","lot_number","auction_date")
QUALITY_FACT_FIELDS=("guide_price","annual_rent","tenure","area_sqft","area_sqm","site_area_acres","tenant","lease_term","lease_start","lease_expiry","break_clause","rent_review","property_type","occupation","epc","rateable_value","fri","development_potential","asset_management","refurbishment","residential_conversion","listed_status","parking","pitch","nearby_occupiers","guarantors","ground_rent","service_charge","erv")
LOT_FIELDS={k for k in Lot.__dataclass_fields__}


def load_old_snapshot():
    p=DATA/"properties.json"
    if not p.exists(): return {"properties":[],"archive":[],"source_health":[]}
    try:
        data=json.loads(p.read_text(encoding="utf-8"))
        return {"properties":data.get("properties",[]),"archive":data.get("archive",[]),"source_health":data.get("source_health",[])}
    except Exception: return {"properties":[],"archive":[],"source_health":[]}


def _key(x): return (str(x.get("source") or "").strip(),str(x.get("url") or "").strip())
def _auction_date(x):
    raw=str(x.get("auction_date") or "").strip()
    if not raw: return None
    try: return datetime.fromisoformat(raw[:10]).date()
    except Exception: return None
def _auction_has_finished(x,today):
    d=_auction_date(x); return bool(d and d<today)
def _normal_status(value): return str(value or "").strip().upper().replace("_"," ")
def _is_terminal(item): return _normal_status(item.get("status")) in TERMINAL_STATUSES
def _complete_authoritative(r):
    return bool(getattr(r,"authoritative_snapshot",False) and r.status=="LIVE" and getattr(r,"expected_count",None) and len(r.lots)==r.expected_count and getattr(r,"scope_dates",()))


def _address_from_url(item):
    url=str(item.get("url") or ""); path=unquote(urlparse(url).path).strip("/")
    if not path: return None
    slug=re.sub(r"-\d{4,7}$","",path.split("/")[-1])
    if slug.lower() in {"current-auction","current-catalogue","property-search","auctions","auction"}: return None
    label=re.sub(r"[-_]+"," ",slug).strip()
    return label.title() if len(label)>=8 and re.search(r"[A-Za-z]",label) else None


def _image_is_valid(source,url):
    if not url: return False
    low=str(url).lower()
    if re.search(r"(?:logo|favicon|sprite|placeholder|avatar|social|brandmark)",low): return False
    src=(source or "").lower()
    if "savills" in src:
        return bool("resize.auctions.savills.co.uk/assets/images/lots/" in low or re.search(r"https?://auctions\.savills\.co\.uk/images/lots/\d+/\d+/[^/?#]+\.(?:jpe?g|png|webp)",low))
    if "acuitus" in src: return "/uploads/" in low and not any(x in low for x in ("banner","header","logo"))
    if "bidx1" in src: return "images-prd.bidx1.com" in low and not any(x in low for x in ("support","agent","surveyor","profile","avatar","team","logo","icon","ber-","user"))
    return True


def _enrich_item(item):
    payload={k:v for k,v in dict(item).items() if k in LOT_FIELDS}
    try:
        lot=Lot(**payload); enriched=enrich_common_fields(lot,str(payload.get("description") or "")).to_dict(); out=dict(item)
        for k,v in enriched.items():
            if k=="source_id": continue
            if out.get(k) in (None,"","UNKNOWN","NOT FOUND") and v not in (None,"","UNKNOWN","NOT FOUND"): out[k]=v
        return out
    except Exception: return dict(item)


def _sanitize_item(item):
    item=_enrich_item(item); repairs=[]
    address=str(item.get("address") or "").strip()
    if not address or len(address)<6 or BAD_ADDRESS.search(address):
        recovered=_address_from_url(item)
        if recovered and not BAD_ADDRESS.search(recovered): item["address"]=recovered; repairs.append("address_from_url")
        else: return None,repairs,"invalid_address"
    url=str(item.get("url") or "").strip()
    if not url.startswith(("http://","https://")): return None,repairs,"invalid_url"
    original_description=str(item.get("description") or ""); cleaned_description=clean_description(original_description)
    if cleaned_description!=original_description: item["description"]=cleaned_description; repairs.append("description_cleaned")
    if item.get("image_url") and not _image_is_valid(item.get("source"),item.get("image_url")): item["image_url"]=None; repairs.append("invalid_image_removed")
    occ=str(item.get("occupation") or "").strip().lower()
    if occ in {"vacant","vacant possession"} and (item.get("annual_rent") is not None or item.get("gross_yield") is not None): item["annual_rent"]=None; item["gross_yield"]=None; repairs.append("vacant_rent_cleared")
    return item,repairs,None


def _meaningful(v): return v not in (None,"","UNKNOWN","NOT FOUND")
def _merge_last_good(old,new):
    if not old: return dict(new)
    out=dict(old)
    for k,v in new.items():
        if k=="description":
            new_desc=clean_description(v); old_desc=clean_description(out.get(k))
            if _meaningful(new_desc): out[k]=new_desc
            elif _meaningful(old_desc): out[k]=old_desc
        elif k=="image_url":
            if _image_is_valid(new.get("source"),v): out[k]=v
        elif k in RICH_FIELDS:
            if _meaningful(v): out[k]=v
        elif _meaningful(v): out[k]=v
    if out.get("guide_price") and out.get("annual_rent"): out["gross_yield"]=round(float(out["annual_rent"])/float(out["guide_price"])*100,2)
    elif str(out.get("occupation") or "").lower() in {"vacant","vacant possession"}: out["gross_yield"]=None
    return out


def _remove_duplicate_images(active):
    by_source=defaultdict(list)
    for item in active: by_source[str(item.get("source") or "Unknown")].append(item)
    removed=0; duplicate_urls={}
    for source,items in by_source.items():
        counts=Counter(str(x.get("image_url") or "").strip() for x in items if x.get("image_url")); bad={u:c for u,c in counts.items() if u and c>=3}
        if not bad: continue
        duplicate_urls[source]=bad
        for item in items:
            if str(item.get("image_url") or "").strip() in bad: item["image_url"]=None; removed+=1
    return removed,duplicate_urls


def _collector_name(fn):
    module=getattr(fn,"__module__","")
    leaf=module.rsplit(".",1)[-1].replace("_v2","").replace("_"," ").strip()
    return leaf.title() or getattr(fn,"__name__","Unknown collector")
def _run_collector_safely(fn):
    try: return fn()
    except Exception as exc:
        source=_collector_name(fn); return SourceResult(source=source,status="FAILED",lots=[],message=f"Collector raised {type(exc).__name__}: {exc}",discovered_count=0,authoritative_snapshot=False)


def run():
    old_snapshot=load_old_snapshot(); old=list(old_snapshot["properties"])+list(old_snapshot["archive"])
    today=datetime.now(timezone.utc).date(); old_by_key={_key(x):dict(x) for x in old if _key(x)!=("","")}
    results=[]; current_by_key={}; source_status={}; authoritative_scopes=[]; quality_repairs=quality_rejections=0; rejection_reasons={}
    for fn in COLLECTORS:
        r=_run_collector_safely(fn); source_status[r.source]=r.status; source_rejected=0
        if r.status in PUBLISHABLE:
            for lot in r.lots:
                item,repairs,reason=_sanitize_item(lot.to_dict()); quality_repairs+=len(repairs)
                if item is None:
                    quality_rejections+=1; source_rejected+=1; rejection_reasons[reason]=rejection_reasons.get(reason,0)+1; continue
                k=_key(item); current_by_key[k]=_merge_last_good(old_by_key.get(k),item)
        status=r.to_status_dict()
        if source_rejected: status["status"]="DEGRADED"; status["message"]=f"{status.get('message','')} Quality gate rejected {source_rejected} unsafe record(s).".strip()
        results.append(status)
        if _complete_authoritative(r) and not source_rejected: authoritative_scopes.append((r.source,set(r.scope_dates)))

    target_coverage=append_missing_health(results)
    merged_by_key=dict(old_by_key); merged_by_key.update(current_by_key); current_keys=set(current_by_key); pruned=0
    for source,scope_dates in authoritative_scopes:
        stale=[k for k,item in merged_by_key.items() if k not in current_keys and item.get("source")==source and str(item.get("auction_date") or "")[:10] in scope_dates]
        for k in stale: merged_by_key.pop(k,None); pruned+=1
    for k,item in merged_by_key.items():
        incoming_terminal=_is_terminal(item)
        if incoming_terminal:
            item["status"]=_normal_status(item.get("status"))
        elif _auction_has_finished(item,today): item["status"]="ARCHIVED"
        elif k in current_keys: item["status"]="CURRENT"
        elif source_status.get(item.get("source")) is not None: item["status"]="STALE SOURCE"
    history=list(merged_by_key.values()); history.sort(key=lambda x:(str(x.get("auction_date") or ""),str(x.get("source") or ""),str(x.get("lot_number") or ""),str(x.get("address") or "")),reverse=True)
    active=[x for x in history if x.get("status")=="CURRENT"]; archive=[x for x in history if x.get("status")!="CURRENT"]
    bad_active=[x for x in active if _auction_has_finished(x,today) or BAD_ADDRESS.search(str(x.get("address") or ""))]
    if bad_active: raise RuntimeError(f"production quality gate failed: {len(bad_active)} unsafe active rows")
    bad_descriptions=[x for x in active if DESCRIPTION_BOILERPLATE.search(str(x.get("description") or ""))]
    if bad_descriptions: raise RuntimeError(f"production description quality gate failed: {len(bad_descriptions)} active rows still contain site chrome")
    terminal_leaks=[x for x in active if _is_terminal(x)]
    if terminal_leaks: raise RuntimeError(f"terminal lifecycle rows leaked into active board: {len(terminal_leaks)}")

    duplicate_image_repairs,duplicate_image_urls=_remove_duplicate_images(active); quality_repairs+=duplicate_image_repairs
    source_quality={}
    for x in active:
        q=source_quality.setdefault(x.get("source") or "Unknown",{"lots":0,"valid_images":0,"rich":0}); q["lots"]+=1
        if _image_is_valid(x.get("source"),x.get("image_url")): q["valid_images"]+=1
        rich=sum(1 for k in QUALITY_FACT_FIELDS if _meaningful(x.get(k)))
        if rich>=4: q["rich"]+=1
    for q in source_quality.values():
        q["image_coverage_pct"]=round(100*q["valid_images"]/q["lots"],1) if q["lots"] else 0; q["rich_coverage_pct"]=round(100*q["rich"]/q["lots"],1) if q["lots"] else 0
    target_coverage=manifest_coverage(results)
    lifecycle_counts=Counter(_normal_status(x.get("status")) for x in archive)
    snapshot={"generated_at":datetime.now(timezone.utc).isoformat(),"properties":active,"archive":archive,"source_health":results,"integrity":{"active_property_count":len(active),"historical_property_count":len(archive),"lifecycle_counts":dict(lifecycle_counts),"authoritative_scopes_completed":len(authoritative_scopes),"stale_false_positive_rows_pruned":pruned,"quality_repairs":quality_repairs,"quality_rejections":quality_rejections,"quality_rejection_reasons":rejection_reasons,"duplicate_image_repairs":duplicate_image_repairs,"duplicate_image_urls":duplicate_image_urls,"source_quality":source_quality,"target_coverage":target_coverage,"acceptance_ready":target_coverage.get("acceptance_ready",False)}}
    (DATA/"properties.json").write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
    print(json.dumps({"generated_at":snapshot["generated_at"],"property_count":len(active),"historical_count":len(archive),"lifecycle_counts":dict(lifecycle_counts),"quality_repairs":quality_repairs,"quality_rejections":quality_rejections,"duplicate_image_repairs":duplicate_image_repairs,"authoritative_scopes_completed":len(authoritative_scopes),"stale_false_positive_rows_pruned":pruned,"source_quality":source_quality,"target_coverage":target_coverage,"sources":results},indent=2))

if __name__=="__main__": run()
