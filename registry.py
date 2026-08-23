from auction_house_london import collect as auction_house_london
from allsop import collect as allsop
from pugh import collect as pugh
from bond_wolfe import collect as bond_wolfe
from savills import collect as savills
from acuitus import collect as acuitus
from base import CollectorResult
from db import replace_snapshot

COLLECTORS=[
    ("Auction House London",auction_house_london),
    ("Allsop Commercial",allsop),
    ("Pugh / BTG Eddisons",pugh),
    ("Bond Wolfe",bond_wolfe),
    ("Savills Auctions",savills),
    ("Acuitus",acuitus),
]

def run_all(max_guide=300000):
    results=[]
    for name,fn in COLLECTORS:
        try:
            results.append(fn(max_guide=max_guide))
        except Exception as exc:
            results.append(CollectorResult(name,"ERROR",[],str(exc)))
    replace_snapshot(results)
    return {
        "lots_seen":sum(len(r.lots) for r in results),
        "sources":[{"source":r.source,"status":r.status,"lots":len(r.lots),"message":r.message} for r in results],
    }
