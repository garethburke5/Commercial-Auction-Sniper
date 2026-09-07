import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, is_commercial, norm
from .utils import nearest_card, detail_lot
from .browser import get_html

SOURCE = "McHugh & Co"
BASE = "https://www.mchughandco.com"
URL = BASE + "/future-auctions/76247"
LANDING_URLS = (URL, BASE + "/pages/auctions", BASE + "/")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _fetch(url):
    last = None
    session = requests.Session()
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if len(r.text) > 1000:
                return BeautifulSoup(r.text, "lxml")
        except Exception as exc:
            last = exc
            time.sleep(0.8 + attempt)
    try:
        return BeautifulSoup(get_html(url, use_browser=False), "lxml")
    except Exception as exc:
        raise exc from last


def _catalogue_soup():
    errors=[]; seen=set(); queue=list(LANDING_URLS)
    while queue:
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try: s=_fetch(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}"); continue
        if any("/lot/details/" in (a.get("href") or "").lower() for a in s.find_all("a",href=True)):
            return s,url
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a.get("href") or "").split("?",1)[0]
            if "/future-auctions/" in href and href not in seen and href not in queue:
                queue.insert(0,href)
    raise RuntimeError("; ".join(errors) or "no McHugh current catalogue could be resolved")


def _auction_date(card):
    m=re.search(r"(?:End Time\s*-\s*|Auction Ended\s*-\s*)?(\d{1,2})/(\d{1,2})/(20\d{2})",card or "")
    if m: return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _terminal_status(text):
    """Read explicit per-lot result labels only.

    Every McHugh bidding page contains generic help text headed 'Withdrawn,
    Postponed and Sold Prior Lots'. Bare phrase matching would therefore mark every
    live lot terminal. The catalogue uses explicit 'Result Sold Prior/Withdrawn'
    labels for actual lot lifecycle changes, so require that evidence.
    """
    probe=norm(text)
    if re.search(r"\bResult\s*:?\s*Sold\s+Prior\b",probe,re.I): return "SOLD PRIOR"
    if re.search(r"\bResult\s*:?\s*Withdrawn(?:\s+Prior)?\b",probe,re.I): return "WITHDRAWN"
    return None


def collect():
    try:
        s,catalogue_url = _catalogue_soup()
        targets = {}
        for a in s.find_all("a", href=True):
            href = urljoin(BASE, a.get("href") or "")
            if "/lot/details/" not in href.lower(): continue
            card = nearest_card(a, 3200)
            if not card or not is_commercial(card): continue
            targets[href] = card

        lots=[]; failures=0; rejected=0; scope_dates=set(); terminal_count=0
        for href, card in targets.items():
            try:
                lot_no=None
                m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I)
                if m: lot_no="Lot "+m.group(1)
                auction_date=_auction_date(card) or "2026-09-16"
                scope_dates.add(auction_date)
                lot=detail_lot(
                    SOURCE,href,seed=card,lot_number=lot_no,auction_date=auction_date,
                    force_commercial=True,use_browser=False,strict_commercial=False,
                    suppress_prior=False,
                )
                if lot:
                    terminal=_terminal_status(card+" "+str(lot.description or ""))
                    if terminal:
                        lot.status=terminal; terminal_count+=1
                    else:
                        lot.status="CURRENT"
                    lots.append(lot)
                else: rejected+=1
            except Exception as e:
                failures+=1; print("MCHUGH_DETAIL_FAIL",href,repr(e))

        return SourceResult(
            SOURCE,"LIVE" if lots and failures==0 else "DEGRADED" if lots else "FAILED",lots,
            f"Current McHugh catalogue via {catalogue_url}: commercial/mixed-use candidates {len(targets)}; {len(lots)} published including {terminal_count} terminal-history lot(s); {rejected} rejected; {failures} detail failures",
            discovered_count=len(targets),scope_dates=tuple(sorted(scope_dates or {"2026-09-16","2026-09-17"})),
        )
    except Exception as e:
        return SourceResult(SOURCE,"FAILED",[],f"McHugh catalogue failed after first-party route and transport fallbacks: {e}")
