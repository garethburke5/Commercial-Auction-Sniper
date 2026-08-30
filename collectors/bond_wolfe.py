import re
from urllib.parse import urljoin
from .core import SourceResult
from .utils import soup, nearest_card, detail_lot

SOURCE="Bond Wolfe"
BASE="https://www.bondwolfe.com"
URL=BASE+"/auctions/properties/"


def _exact_property_image(detail_soup, page_url):
    """Return the Bond Wolfe lot photograph, never the site-wide header image.

    Bond Wolfe lot pages include an unrelated inspiration-insight.com image near
    the top of the document. The actual lot gallery is served by EIG from
    cdn.eigpropertyauctions.co.uk/ams/images/... and is identifiable by that
    auction-image path. Prefer the medium/large gallery image.
    """
    candidates=[]
    for tag in detail_soup.find_all(["img", "source", "a"]):
        vals=[]
        for attr in ("src", "data-src", "data-lazy-src", "data-original", "href"):
            v=tag.get(attr)
            if v:
                vals.append(v)
        for attr in ("srcset", "data-srcset"):
            ss=tag.get(attr)
            if ss:
                vals.extend(part.strip().split(" ")[0] for part in ss.split(",") if part.strip())
        for v in vals:
            u=urljoin(page_url,v)
            low=u.lower()
            if "cdn.eigpropertyauctions.co.uk/ams/images/" not in low:
                continue
            if any(x in low for x in ("logo","icon","placeholder","map","floorplan")):
                continue
            score=0
            if "web_large" in low: score+=30
            if "web_medium" in low: score+=25
            if "web_small" in low: score+=10
            if re.search(r"/auction/\d+/\d+_web_",low): score+=20
            candidates.append((score,u))
    if not candidates:
        raw=str(detail_soup).replace("\\/","/")
        for u in re.findall(r'https://cdn\.eigpropertyauctions\.co\.uk/ams/images/[^"\'<>\s]+',raw,re.I):
            low=u.lower()
            if any(x in low for x in ("logo","icon","placeholder","map","floorplan")):
                continue
            score=(30 if "web_large" in low else 25 if "web_medium" in low else 10 if "web_small" in low else 0)
            candidates.append((score,u))
    if not candidates:
        return None
    candidates.sort(key=lambda x:(x[0],len(x[1])),reverse=True)
    return candidates[0][1]


def collect():
    try:
        s=soup(URL,use_browser=True)
        seen,lots=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if not re.match(r"^https://www\.bondwolfe\.com/auctions/properties/\d+-property-auction-[^/]+/?$",href,re.I):
                continue
            href=href.rstrip("/")+"/"
            if href in seen: continue
            seen.add(href)
            card=nearest_card(a)
            lot=detail_lot(SOURCE,href,seed=card,auction_date="2026-09-10",force_commercial=False,use_browser=True)
            if lot:
                try:
                    ds=soup(href,use_browser=False)
                    exact=_exact_property_image(ds,href)
                    if exact:
                        lot.image_url=exact
                except Exception:
                    pass
                lots.append(lot)
        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,f"10 Sep exact property URLs: {len(lots)} commercial/mixed-use lots")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
