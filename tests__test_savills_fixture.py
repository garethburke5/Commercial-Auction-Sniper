
import re
from bs4 import BeautifulSoup
from collectors__core import norm, parse_guide, parse_rent

FIXTURE = """
<div>Lot 73</div><div>Guide Price £135,000</div>
<section><a href="/auctions/2-september-2026-241/26-market-street-crewe-cheshire-cw1-2el-24071">26 Market Street, Crewe, Cheshire CW1 2EL</a></section>
<ul><li>Freehold Retail Investment</li><li>Investment let at £15,000 pa (11.11% GIY on Guide Price)</li></ul>
<div>Lot 97</div><div>Guide Price £65,000</div><div>Sold Prior</div>
<section><a href="/auctions/2-september-2026-241/51-market-place-whitehaven-ca28-7jb">51 Market Place, Whitehaven, CA28 7JB</a></section>
<div>Lot 98</div><div>Guide Price £140,000</div>
<section><a href="/auctions/2-september-2026-241/66-70-high-street-mexborough-south-yorkshire-s64-9au-24591">66-70 High Street, Mexborough, South Yorkshire, S64 9AU</a></section>
<ul><li>Investment Let at £25,600 p.a. (18.28% GIY on Guide Price)</li></ul>
"""

def before(a):
    vals=[]
    for s in a.find_all_previous(string=True,limit=50):
        t=norm(str(s))
        if t: vals.append(t)
    vals.reverse()
    return vals

def after(a):
    vals=[]
    for s in a.find_all_next(string=True,limit=70):
        t=norm(str(s))
        if not t: continue
        if vals and re.fullmatch(r"Lot\s+\d+[A-Z]?",t,re.I): break
        vals.append(t)
    return vals

def parse_fixture():
    s=BeautifulSoup(FIXTURE,"lxml")
    out={}
    for a in s.find_all("a"):
        b=before(a)
        idx=None;lot=None
        for i in range(len(b)-1,-1,-1):
            m=re.fullmatch(r"Lot\s+(\d+[A-Z]?)",b[i],re.I)
            if m: idx=i;lot="Lot "+m.group(1);break
        pre=" ".join(b[idx:])
        post=" ".join(after(a))
        out[lot]={
            "guide":parse_guide(pre),
            "rent":parse_rent(post),
            "sold":"sold prior" in pre.lower()
        }
    return out

def test_savills_fixture_boundaries():
    x=parse_fixture()
    assert x["Lot 73"] == {"guide":135000,"rent":15000,"sold":False}
    assert x["Lot 97"]["sold"] is True
    assert x["Lot 98"] == {"guide":140000,"rent":25600,"sold":False}
