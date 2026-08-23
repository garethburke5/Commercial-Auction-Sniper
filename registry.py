from auction_house_london import collect as ahl
from allsop import collect as allsop
from pugh import collect as pugh
from bond_wolfe import collect as bond_wolfe
from savills import collect as savills
from acuitus import collect as acuitus
from db import replace_snapshot
from base import CollectorResult
COLLECTORS=[("Auction House London",ahl),("Allsop Commercial",allsop),("Pugh / BTG Eddisons",pugh),("Bond Wolfe",bond_wolfe),("Savills Auctions",savills),("Acuitus",acuitus)]
def run_all(max_guide=300000):
    results=[]
    for name,fn in COLLECTORS:
        try:results.append(fn(max_guide=max_guide))
        except Exception as e:results.append(CollectorResult(name,"ERROR",[],str(e)))
    replace_snapshot(results)
    return {"lots_seen":sum(len(r.lots) for r in results),"sources":[r.as_dict() for r in results]}
