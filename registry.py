from auction_house_london import collect as collect_ahl
from pugh import collect as collect_pugh
from savills import collect as collect_savills
from allsop import collect as collect_allsop
from acuitus import collect as collect_acuitus
from db import upsert_lots,record_scan

COLLECTORS=[
("Auction House London",collect_ahl),
("Pugh / BTG Eddisons",collect_pugh),
("Savills Auctions",collect_savills),
("Allsop Commercial",collect_allsop),
("Acuitus",collect_acuitus),
]

def run_all(max_guide=300000):
    summary=[];total=0
    for name,fn in COLLECTORS:
        try:
            result=fn(max_guide=max_guide)
            if result.lots:
                upsert_lots([x.as_dict() for x in result.lots])
                total+=len(result.lots)
            record_scan(result.source,result.status,len(result.lots),result.message)
            summary.append(result.as_dict())
        except Exception as e:
            record_scan(name,"ERROR",0,str(e))
            summary.append({"source":name,"status":"ERROR","lots":0,"message":str(e)})
    return {"sources":summary,"lots_seen":total}
