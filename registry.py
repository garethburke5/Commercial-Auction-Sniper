from allsop import collect as allsop
from pugh import collect as pugh
from savills import collect as savills
from acuitus import collect as acuitus
from db import upsert_lots,record_scan
COLLECTORS=[
("Allsop Commercial",allsop),
("Pugh / BTG Eddisons",pugh),
("Savills Auctions",savills),
("Acuitus",acuitus),
]
def run_all(max_guide=300000):
    summary=[];total=0
    for name,fn in COLLECTORS:
        try:
            r=fn(max_guide=max_guide)
            if r.lots:upsert_lots([x.as_dict() for x in r.lots]);total+=len(r.lots)
            record_scan(r.source,r.status,len(r.lots),r.message);summary.append(r.as_dict())
        except Exception as e:
            record_scan(name,"ERROR",0,str(e));summary.append({"source":name,"status":"ERROR","lots":0,"message":str(e)})
    return {"sources":summary,"lots_seen":total}
