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

    An explicit postponement/reschedule outranks the generic page date. This keeps
    future commercial lots alive when they remain in the current catalogue after
    being moved to a later sale.
    """
    text = norm(text)
    patterns = (
        (r"to be offered in our\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?\s+auction", True),
        (r"postponed until\s+(?:(\d{1,2})(?:st|nd|rd|th)?\s+)?([A-Za-z]+)\s+(20\d{2})\s+auction", False),
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
        # Month-only postponements (e.g. "POSTPONED UNTIL OCTOBER 2026 AUCTION")
        # have no exact sale day yet; retain the known current date until Strettons
        # publishes the exact future date instead of manufacturing a day.
        if day is None:
            return fallback
        year = (year or fallback_year) if may_omit_year else year
        for fmt in ("%d %B %Y", "%d %b %Y", "%d %b %y"):
            try:
                raw = f"{day} {month} {year}"
                return datetime.strptime(raw, fmt).date().isoformat()
            except Exception:
                pass
    return fallback


def _expected(text):
    for pat in [r"(\d+)\s+auction commercial properties for sale", r"(\d+)\s+commercial properties for sale"]:
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


def _lot_terminal_status(text):
    """Classify only explicit lifecycle evidence on the current Strettons lot page."""
    probe = norm(text)
    if re.search(r"\bsold\s+prior\s+to\s+auction\b|\bsold\s+prior\b", probe, re.I):
        return "SOLD PRIOR"
    if re.search(r"\bwithdrawn(?:\s+prior)?\b|\blot\s+withdrawn\b", probe, re.I):
        return "WITHDRAWN"
    # Strettons also displays a simple Sold badge plus a sold price on completed lots.
    if re.search(r"\bSold\b.{0,180}\bSold\s+(?:for|at)\s+£", probe, re.I):
        return "COMPLETED"
    return None


def _fully_rendered_commercial():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1400}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36")
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
                    button.first.click(timeout=6000); page.wait_for_timeout(900)
                    after = len(page.locator("a[href*='auction-commercial-property-for-sale'], a[href*='auction-mixed-use-property-for-sale']").all())
                    if after <= before and not button.first.is_visible():
                        break
                except Exception:
                    break
            html = page.content(); browser.close(); return BeautifulSoup(html, "lxml")
    except Exception as exc:
        print("STRETTONS_LOAD_MORE_FAIL", repr(exc)); return None


def collect():
    try:
        today = date.today().isoformat()
        try: current_s = soup(CURRENT, use_browser=False)
        except Exception: current_s = soup(CURRENT, use_browser=True)
        current_text = norm(current_s.get_text(" ", strip=True))
        current_auction_date = _parse_current_date(current_text)
        if not current_auction_date:
            return SourceResult(SOURCE, "FAILED", [], "Could not discover Strettons next/current auction date.")

        advertised = None; targets = {}
        for use_browser in (False, True):
            try: candidate = soup(COMMERCIAL, use_browser=use_browser)
            except Exception as exc:
                print("STRETTONS_INDEX_FAIL", use_browser, repr(exc)); continue
            text = norm(candidate.get_text(" ", strip=True)); advertised = _expected(text) or advertised
            found = _targets(candidate)
            if len(found) > len(targets): targets = found
            if advertised and len(targets) >= advertised: break
        if advertised and len(targets) < advertised:
            rendered = _fully_rendered_commercial()
            if rendered is not None:
                advertised = _expected(norm(rendered.get_text(" ", strip=True))) or advertised
                targets.update(_targets(rendered))
        if not targets:
            return SourceResult(SOURCE, "FAILED", [], f"Discovered current auction {current_auction_date}, but index returned no commercial detail links after static+rendered retrieval.", expected_count=advertised, discovered_count=0, authoritative_snapshot=False, scope_dates=(current_auction_date,))

        lots=[]; failures=0; terminal_count=0; historic_count=0; rescheduled_count=0
        for href,(card,lot_no) in targets.items():
            lot=None; last_exc=None
            for use_browser in (False,True):
                try:
                    ds=soup(href,use_browser=use_browser)
                    main=ds.find("main") or ds
                    detail_text=norm(main.get_text(" ",strip=True))
                    lot_date=_parse_detail_auction_date(detail_text+" "+card,current_auction_date)
                    terminal=_lot_terminal_status(detail_text)
                    lot=detail_lot(SOURCE,href,seed=card,lot_number=lot_no,auction_date=lot_date,force_commercial=True,use_browser=use_browser,suppress_prior=False)
                    if lot:
                        if terminal:
                            lot.status=terminal; terminal_count+=1
                        elif lot_date and lot_date < today:
                            lot.status="ARCHIVED"; historic_count+=1
                        else:
                            lot.status="CURRENT"
                            if lot_date and lot_date != current_auction_date: rescheduled_count+=1
                        break
                except Exception as exc:
                    last_exc=exc
            if lot: lots.append(lot)
            else:
                failures+=1; print("STRETTONS_DETAIL_FAIL",href,repr(last_exc))

        expected=len(targets)
        status="LIVE" if failures==0 and len(lots)==expected else "DEGRADED" if lots else "FAILED"
        scope_dates=tuple(sorted({str(x.auction_date)[:10] for x in lots if x.auction_date}))
        return SourceResult(
            SOURCE,status,lots,
            f"Commercial result set advertises {advertised if advertised is not None else 'unknown'} entries; {len(targets)} exact links discovered; {sum(1 for x in lots if x.status=='CURRENT')} current/future, {terminal_count} sold/withdrawn, {historic_count} historic, {rescheduled_count} explicitly rescheduled; {failures} parse failures. All discovered commercial rows are preserved with lifecycle status.",
            expected_count=expected, discovered_count=len(targets), authoritative_snapshot=(status=="LIVE"), scope_dates=scope_dates,
        )
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Strettons discovery failed: {exc}")
