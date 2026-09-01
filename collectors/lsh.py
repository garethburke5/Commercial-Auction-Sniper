from urllib.parse import urljoin
from .core import SourceResult, is_commercial
from .utils import soup, nearest_card, detail_lot

SOURCE="LSH Auctions"
BASE="https://propertyauctions.lsh.co.uk"
URL=BASE+"/future-auctions"
AUCTION_DATE="2026-09-09"


def _catalogue(use_browser=False):
    return soup(URL,use_browser=use_browser)


def collect():
    try:
        try:
            s=_catalogue(False)
        except Exception:
            s=_catalogue(True)

        page_text=s.get_text(" ",strip=True)
        sale_context=("9 September 2026" in page_text or "09/09/2026" in page_text or "9 Sep" in page_text)
        seen,targets=set(),[]
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a["href"])
            if href in seen or href.rstrip("/")==URL.rstrip("/"):
                continue
            card=nearest_card(a,4200)
            if not is_commercial(card):
                continue
            # The sale date is often rendered at catalogue level rather than
            # repeated inside every property card.
            if not sale_context and "9 September 2026" not in card and "09/09/2026" not in card and "9 Sep" not in card:
                continue
            if not any(x in href.lower() for x in ("property","lot","auction")):
                continue
            seen.add(href)
            targets.append((href,card))

        lots=[]; failures=0
        for href,card in targets:
            lot=None
            try:
                lot=detail_lot(SOURCE,href,seed=card,auction_date=AUCTION_DATE,
                               force_commercial=False,use_browser=False)
            except Exception:
                try:
                    lot=detail_lot(SOURCE,href,seed=card,auction_date=AUCTION_DATE,
                                   force_commercial=False,use_browser=True)
                except Exception as e:
                    failures+=1
                    print("LSH_DETAIL_FAIL",href,repr(e))
            if lot:
                lots.append(lot)

        status="LIVE" if lots else "FAILED"
        return SourceResult(SOURCE,status,lots,
                            f"9 Sep commercial/mixed-use candidates {len(targets)}; {len(lots)} published; {failures} detail failures")
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
