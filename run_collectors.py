
from pathlib import Path
import json
from datetime import datetime, timezone

from collectors.auction_house_london import collect as ahl
from collectors.savills import collect as savills
from collectors.bond_wolfe_v2 import collect as bond_wolfe
from collectors.pugh import collect as pugh
from collectors.strettons import collect as strettons
from collectors.lsh import collect as lsh
from collectors.acuitus import collect as acuitus
from collectors.pattinson import collect as pattinson
from collectors.pending import allsop, clive_emson, mchugh

DATA = Path("data")
DATA.mkdir(exist_ok=True)

COLLECTORS = [ahl, savills, bond_wolfe, pugh, strettons, lsh, pattinson, allsop, acuitus, clive_emson, mchugh]

def load_old():
    p=DATA/"properties.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("properties",[])
    except Exception:
        return []

def run():
    old = load_old()
    old_by_source = {}
    for x in old:
        old_by_source.setdefault(x["source"], []).append(x)

    results=[]
    merged=[]

    for fn in COLLECTORS:
        r=fn()
        results.append(r.to_status_dict())

        if r.status=="LIVE":
            merged.extend([x.to_dict() for x in r.lots])
        elif r.source in old_by_source:
            # Preserve last known good data for a failed source, visibly marked stale.
            for x in old_by_source[r.source]:
                y=dict(x)
                y["status"]="STALE SOURCE"
                merged.append(y)

    # de-dupe exact source/url
    unique={}
    for x in merged:
        unique[(x["source"],x["url"])]=x
    merged=list(unique.values())

    snapshot={
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "properties":merged,
        "source_health":results,
    }
    (DATA/"properties.json").write_text(json.dumps(snapshot,indent=2),encoding="utf-8")
    print(json.dumps({"generated_at":snapshot["generated_at"],"property_count":len(merged),"sources":results},indent=2))

if __name__=="__main__":
    run()
