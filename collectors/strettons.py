import re
from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .core import SourceResult, norm
from .utils import soup, detail_lot, nearest_card

SOURCE = "Strettons"
BASE = "https://www.strettons.co.uk"
CURRENT = BASE + "/auctions/current-catalogue/"
COMMERCIAL = BASE + "/auction-commercial-property/for-sale/"


def _parse_current_date(text):
    patterns = [
        r"(?:Next Auction:\s*)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})",
        r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\s*-\s*Lot",
    ]
    for i, pat in enumerate(patterns):
        m = re.search(pat, text, re.I)
        if not m:
            continue
        try:
            fmt = "%d %B %Y" if i == 0 else "%d %b %y"
            return datetime.strptime(" ".join(m.groups()), fmt).date().isoformat()
        except Exception:
            pass
    return None


def _parse_detail_auction_date(text, fallback=None):
    """Return the lot's actual advertised auction date.

    Strettons can leave a rescheduled lot inside the current catalogue while the lot
    card still carries the old date. An explicit 'to be offered in our <date> auction'
    therefore outranks the generic page date, followed by the lot-page date itself.
    """
    text = norm(text)
    patterns = (
        (r"to be offered in our\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?\s+auction", True),
        (r"to be auctioned[^\d]{0,80}(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", False),
        (r"\b(?:Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun)[a-z]*\s+(\d{1,2})\s+([A-Za-z]{3,9})\s+(20\d{2})\b", False),
        (r"\b(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2})\s*-\s*Lot\b", False),
    )
    fallback_year = str(fallback or "")[:4] if fallback else str(date.today().year)
    for pat, may_omit_year in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        day, month, year = m.groups()
        year = (year or fallback_year) if may_omit_year else year
        for fmt in ("%d %B %Y", "%d %b %Y", "%d %b %y"):
            try:
                raw = f"{day} {month} {year}"
                return datetime.strptime(raw, fmt).date().isoformat()
            except Exception:
                pass
    return fallback


def _expected(text):
    for pat in [
        r"(\d+)\s+auction commercial properties for sale",
        r"(\d+)\s+commercial properties for sale",
    ]:
        m = re.search(pat, text, re.I)
        if m:
            return int(m.group(1))
    return None


def _lot_no(text):
    m = re.search(r"(?:\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\s*-\s*)?Lot\s+(\d+[A-Z]?)", text, re.I)
    return "Lot " + m.group(1) if m else None


def _targets(s):
    out = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        low = href.lower()
        if "strettons.co.uk" not in low:
            continue
        if not any(x in low for x in ("auction-commercial-property-for-sale", "auction-mixed-use-property-for-sale")):
            continue
        card = nearest_card(a, 3200) or norm(a.get_text(" ", strip=True))
        out.setdefault(href, (card, _lot_no(card)))
    return out


def _fully_rendered_commercial():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1400},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
            )
            page.goto(COMMERCIAL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            for _ in range(12):
                button = page.get_by_role("button", name=re.compile(r"load more", re.I))
                if button.count() == 0:
                    break
                try:
                    if not button.first.is_visible():
                        break
                    before = len(page.locator("a[href*='auction-commercial-property-for-sale'], a[href*='auction-mixed-use-property-for-sale']").all())
                    button.first.click(timeout=6000)
                    page.wait_for_timeout(900)
                    after = len(page.locator("a[href*='auction-commercial-property-for-sale'], a[href*='auction-mixed-use-property-for-sale']").all())
                    if after <= before and not button.first.is_visible():
                        break
                except Exception:
                    break
            html = page.content()
            browser.close()
            return BeautifulSoup(html, "lxml")
    except Exception as exc:
        print("STRETTONS_LOAD_MORE_FAIL", repr(exc))
        return None


def collect():
    try:
        today = date.today().isoformat()
        try:
            current_s = soup(CURRENT, use_browser=False)
        except Exception:
            current_s = soup(CURRENT, use_browser=True)
        current_text = norm(current_s.get_text(" ", strip=True))
        current_auction_date = _parse_current_date(current_text)
        if not current_auction_date:
            return SourceResult(SOURCE, "FAILED", [], "Could not discover Strettons next/current auction date.")

        expected = None
        targets = {}
        for use_browser in (False, True):
            try:
                candidate = soup(COMMERCIAL, use_browser=use_browser)
            except Exception as exc:
                print("STRETTONS_INDEX_FAIL", use_browser, repr(exc))
                continue
            text = norm(candidate.get_text(" ", strip=True))
            expected = _expected(text) or expected
            found = _targets(candidate)
            if len(found) > len(targets):
                targets = found
            if expected and len(targets) >= expected:
                break

        if expected and len(targets) < expected:
            rendered = _fully_rendered_commercial()
            if rendered is not None:
                expected = _expected(norm(rendered.get_text(" ", strip=True))) or expected
                targets.update(_targets(rendered))

        if not targets:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Discovered current auction {current_auction_date}, but index returned no commercial detail links after static+rendered retrieval.",
                expected_count=expected, discovered_count=0,
                authoritative_snapshot=False, scope_dates=(current_auction_date,),
            )

        lots = []
        failures = 0
        for href, (card, lot_no) in targets.items():
            lot = None
            for use_browser in (False, True):
                try:
                    ds = soup(href, use_browser=use_browser)
                    detail_text = norm((ds.find("main") or ds).get_text(" ", strip=True))
                    lot_date = _parse_detail_auction_date(detail_text + " " + card, current_auction_date)
                    if not lot_date or lot_date < today:
                        lot = None
                        break
                    lot = detail_lot(
                        SOURCE, href, seed=card, lot_number=lot_no,
                        auction_date=lot_date, force_commercial=True,
                        use_browser=use_browser, suppress_prior=True,
                    )
                    if lot:
                        break
                except Exception as exc:
                    if use_browser:
                        failures += 1
                        print("STRETTONS_DETAIL_FAIL", href, repr(exc))
            if lot and str(lot.auction_date or "")[:10] >= today:
                lots.append(lot)

        if not lots:
            return SourceResult(
                SOURCE, "FAILED", [],
                f"Discovered current catalogue {current_auction_date} and {len(targets)} commercial detail links, but no valid current/future lots parsed.",
                expected_count=expected, discovered_count=len(targets),
                authoritative_snapshot=False, scope_dates=(current_auction_date,),
            )

        scope_dates = tuple(sorted({str(x.auction_date)[:10] for x in lots if x.auction_date}))
        rescheduled = [x for x in lots if str(x.auction_date)[:10] != current_auction_date]
        # The advertised commercial count describes the result set shown on this
        # catalogue page, which can include a lot explicitly rescheduled to a later
        # auction. Reconcile against all qualifying displayed lots, not only the
        # original current-auction date, or a valid reschedule creates a false count
        # mismatch and blocks publication.
        status = "LIVE" if expected and len(lots) == expected and failures == 0 else "DEGRADED"
        return SourceResult(
            SOURCE, status, lots,
            f"Dynamic catalogue: page anchored to {current_auction_date}; expected {expected if expected else 'unknown'} displayed commercial lots; {len(targets)} exact links discovered; {len(lots)} current/future lots published including {len(rescheduled)} explicitly rescheduled lot(s); {failures} failures.",
            expected_count=expected,
            discovered_count=len(targets),
            authoritative_snapshot=(status == "LIVE"),
            scope_dates=scope_dates,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Strettons discovery failed: {exc}")
