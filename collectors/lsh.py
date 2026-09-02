import re
from urllib.parse import urljoin
from .core import SourceResult, is_commercial, norm
from .utils import soup, detail_lot

SOURCE="LSH Auctions"
BASE="https://propertyauctions.lsh.co.uk"
URL=BASE+"/future-auctions"
AUCTION_DATE="2026-09-09"


def _catalogue(use_browser=False):
    return soup(URL,use_browser=use_browser)


def _card_text(a):
    node=a
    best=""
    for _ in range(8):
        node=getattr(node,"parent",None)
        if node is None:
            break
        txt=norm(node.get_text(" ",strip=True))
        if 40 <= len(txt) <= 5000:
            best=txt
        if "Auction Date" in txt and "Guide Price" in txt and len(txt) <= 5000:
            return txt
    return best


def _commercial_card(text):
    low=norm(text).lower()
    # First use the shared classifier, then allow source-specific phrases that
    # are clearly commercial but absent from the generic taxonomy.
    if is_commercial(text):
        return True
    source_terms=(
        "coaching inn", "business centre", "grade a office", "office accommodation",
        "industrial unit", "commercial space", "coffee shop", "café/bar", "cafe/bar",
        "public house", "former hotel", "former bank", "retail premises", "showroom",
        "shop & café", "shop and café", "mixed-use building", "mixed use building",
    )
    return any(x in low for x in source_terms)


def collect():
    try:
        try:
            s=_catalogue(False)
        except Exception:
            s=_catalogue(True)

        page_text=norm(s.get_text(" ",strip=True))
        sale_context=bool(re.search(r"9(?:th)?\s+September\s+2026|09/09/2026|9\s+Sep",page_text,re.I))
        targets={}
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a.get("href") or "")
            # LSH's live lot links are stable GUID routes under /lot/details/.
            if "/lot/details/" not in href.lower():
                continue
            card=_card_text(a)
            if not card or not _commercial_card(card):
                continue
            if not sale_context and not re.search(r"9(?:th)?\s+September\s+2026|09/09/2026|9\s+Sep",card,re.I):
                continue
            low=card.lower()
            if "withdrawn" in low or "sold prior" in low:
                continue
            targets[href]=card

        lots=[]; failures=0; rejected=0
        for href,card in targets.items():
            lot=None
            try:
                lot=detail_lot(
                    SOURCE,href,seed=card,auction_date=AUCTION_DATE,
                    # Candidate is positively classified from LSH's catalogue;
                    # avoid losing it to a second generic classification pass.
                    force_commercial=True,use_browser=False
                )
            except Exception:
                try:
                    lot=detail_lot(
                        SOURCE,href,seed=card,auction_date=AUCTION_DATE,
                        force_commercial=True,use_browser=True
                    )
                except Exception as e:
                    failures+=1
                    print("LSH_DETAIL_FAIL",href,repr(e))
            if lot:
                lots.append(lot)
            else:
                rejected+=1

        status="LIVE" if lots else "FAILED"
        return SourceResult(
            SOURCE,status,lots,
            f"9 Sep commercial/mixed-use candidates {len(targets)}; {len(lots)} published; {rejected} rejected; {failures} detail failures"
        )
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],str(e))
