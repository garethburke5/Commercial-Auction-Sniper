import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin

from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, nearest_card

SOURCE = "Auction House London"
URL = "https://auctionhouselondon.co.uk/auction/september-2-3-2026"
AHL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": URL,
}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def _first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text or "", re.I)
        if m:
            return norm(m.group(1))
    return None


def _derive_expiry(start, years):
    if not start or not years:
        return None
    raw = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", norm(start), flags=re.I)
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y"):
        try:
            d = datetime.strptime(raw, fmt)
            y = d.year + int(float(years))
            try:
                out = d.replace(year=y)
            except ValueError:
                out = d.replace(year=y, day=28)
            return out.strftime("%d %B %Y").lstrip("0")
        except Exception:
            pass
    return None


def _section(text, name, next_names):
    tail = "|".join(re.escape(x) for x in next_names)
    return _first([
        rf"{re.escape(name)}\s+(.+?)(?=(?:{tail})\s+|Financial Tools|Legal Pack|Additional Fees|Similar Properties|$)"
    ], text)


def _ahl_card_is_commercial(card):
    low = (card or "").lower()
    strong = (
        "commercial property", "retail property", "industrial development",
        "industrial property", "industrial building", "commercial investment",
        "commercial unit", "commercial building", "commercial premises",
        "retail investment", "retail unit", "shop investment", "shop unit",
        "office investment", "office unit", "warehouse", "workshop",
        "restaurant", "public house", " pub ", "hotel", "care home",
        "business premises", "mixed use", "mixed-use", "commercial/residential",
        "commercial / residential", "vaults", "tunnels",
    )
    if any(x in low for x in strong):
        return True
    return bool(
        re.search(r"\b(?:land|development)\b", low)
        and re.search(r"\b(?:industrial|commercial|retail|office|warehouse|workshop|business|garage block|storage|yard)\b", low)
    )


def _card_address(card):
    text = norm(card)
    m = re.search(
        r"\b(?:Freehold|Leasehold)\s+(.+?\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b)",
        text,
        re.I,
    )
    return norm(m.group(1)) if m else None


def _card_property_type(card):
    text = norm(card)
    m = re.search(
        r"(?:Guide Price:\s*£[\d,]+(?:\s*-\s*£[\d,]+|\+)?)\s+(.+?)\s+(Freehold|Leasehold)\b",
        text,
        re.I,
    )
    if m:
        return norm(m.group(1))
    for label in (
        "Workshop & Retail space", "Retail Property (high street)", "Retail Property",
        "Commercial Property", "Industrial Development", "Industrial Property",
        "Office", "Restaurant", "Care Home", "Mixed Use",
    ):
        if label.lower() in text.lower():
            return label
    return None


def _lot_from_card(href, card, lotno):
    address = _card_address(card) or href.rstrip("/").split("/lot/", 1)[-1].rsplit("-", 1)[0].replace("-", " ").title()
    vacant = bool(re.search(r"\bVacant\b", card, re.I))
    rent = None if vacant else parse_rent(card)
    lot = Lot(
        source=SOURCE,
        url=href,
        address=address,
        lot_number=lotno,
        auction_date="2026-09-02",
        guide_price=parse_guide(card),
        annual_rent=rent,
        tenure=parse_tenure(card),
        vat_status=parse_vat(card),
        legal_pack_status="NOT CHECKED",
        status="Live",
        description=norm(card)[:3000],
        property_type=_card_property_type(card),
        occupation="Vacant" if vacant else ("Tenanted" if rent else None),
    )
    if re.search(r"development|planning permission|potential for", card, re.I):
        lot.development_potential = True
    if re.search(r"residential|HMO|House in Multiple Occupation", card, re.I) and lot.development_potential:
        lot.residential_conversion = True
    if re.search(r"secure yard|yard", card, re.I):
        lot.parking = "Secure yard"
    return lot.finalise()


def _looks_like_exact(ds, base):
    main = ds.find("main") or ds
    text = norm(main.get_text(" ", strip=True))
    if len(text) < 1200:
        return False
    postcode = _first([r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b"], base.address or "")
    postcode_ok = not postcode or postcode.replace(" ", "").lower() in text.replace(" ", "").lower()
    detail_markers = sum(bool(re.search(rf"\b{x}\b", text, re.I)) for x in ("Tenure", "Accommodation", "Tenancy", "Planning", "VAT", "EPC"))
    return postcode_ok and detail_markers >= 2


def _rich_detail(lot, ds):
    main = ds.find("main") or ds
    text = norm(main.get_text(" ", strip=True))
    text = re.split(r"\bSimilar Properties\b", text, 1, flags=re.I)[0]

    lm = re.search(r"\bLot\s+(\d+[A-Z]?)\b", text, re.I)
    if lm:
        lot.lot_number = "Lot " + lm.group(1)

    gm = re.search(r"Guide Price\s*:?\s*£\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if gm:
        lot.guide_price = _num(gm.group(1))

    tenure_sec = _section(text, "Tenure", ["Location", "Accommodation", "Planning", "Tenancy", "VAT", "EPC Rating", "Exterior", "Note"])
    if tenure_sec:
        tm = re.search(r"\b(Freehold|Leasehold)\b", tenure_sec, re.I)
        if tm:
            lot.tenure = tm.group(1).title()
        yrs = _first([r"approximately\s+(\d+(?:\.\d+)?)\s+years? unexpired"], tenure_sec)
        if yrs:
            lot.lease_term = f"Approximately {yrs} years unexpired"
        elif re.search(r"999\s+years", tenure_sec, re.I):
            lot.lease_term = "999 years"
        gr = _first([r"(?:passing )?ground rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?)"], tenure_sec)
        if gr:
            lot.ground_rent = _num(gr)
        elif re.search(r"peppercorn ground rent", tenure_sec, re.I):
            lot.ground_rent = 0.0

    accom = _section(text, "Accommodation", ["Exterior", "Planning", "Tenancy", "VAT", "EPC Rating", "Note"])
    if accom:
        pairs = re.findall(r"([\d,]+(?:\.\d+)?)\s*sq\s*m\s*\(([\d,]+(?:\.\d+)?)\s*sq\s*ft\)", accom, re.I)
        if pairs:
            vals = [(_num(a), _num(b)) for a, b in pairs]
            lot.area_sqm = round(sum(a for a, _ in vals if a), 2)
            lot.area_sqft = round(sum(b for _, b in vals if b), 2)
        else:
            sqm = [_num(x) for x in re.findall(r"(?:G\.I\.A\.?\s*)?(?:Approximately\s*)?([\d,]+(?:\.\d+)?)\s*sq\s*m", accom, re.I)]
            if sqm:
                lot.area_sqm = round(sum(x for x in sqm if x), 2)
                lot.area_sqft = round(lot.area_sqm * 10.7639, 0)

    epc = _first([r"EPC Rating\s+([A-G])\b", r"Energy Performance Rating\s+([A-G])\b"], text)
    if epc:
        lot.epc = epc.upper()

    tenancy = _section(text, "Tenancy", ["VAT", "EPC Rating", "Planning", "Joint Agent", "Note"])
    headline = text[:1800]
    vacant = bool(re.search(r"\bVacant\b", headline, re.I))
    current = _first([
        r"Fully Let Producing\s*£\s*([\d,]+(?:\.\d+)?)\s*Per Annum",
        r"Let Producing\s*£\s*([\d,]+(?:\.\d+)?)\s*Per Annum",
        r"at a rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
        r"rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*per annum",
    ], tenancy or headline)
    if vacant:
        lot.annual_rent = None
        lot.occupation = "Vacant"
    elif current:
        lot.annual_rent = _num(current)
        lot.occupation = "Tenanted"

    if tenancy and not vacant:
        tenant = _first([
            r"(?:let|leased) to\s+(.+?)\s+for a term",
            r"(?:let|leased) to\s+(.+?)\s+(?:on|at a rent|commencing)",
        ], tenancy)
        if tenant and len(tenant) < 120:
            lot.tenant = tenant
        start = _first([
            r"commencing\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
            r"from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        ], tenancy)
        term = _first([r"term of\s+(\d+(?:\.\d+)?\s*years?)"], tenancy)
        if start:
            lot.lease_start = start
        if term:
            lot.lease_term = term
            y = re.search(r"\d+(?:\.\d+)?", term)
            if start and y:
                lot.lease_expiry = _derive_expiry(start, y.group(0))
        if re.search(r"\bFRI\b|full repairing and insuring", tenancy, re.I):
            lot.fri = True
        review = _first([
            r"(\d+[- ]yearly RPI index linked reviews?)",
            r"(RPI index linked reviews?[^.;]{0,80})",
            r"(rent reviews?[^.;]{0,100})",
        ], tenancy)
        if review:
            lot.rent_review = review
        br = _first([r"(Tenant(?:'s)? break clause\s+20\d{2})", r"(break clause[^.;]{0,80})"], tenancy)
        if br:
            lot.break_clause = br
        if re.search(r"did not exercise (?:their )?break clause", tenancy, re.I):
            lot.break_status = "PASSED"
            lot.break_clause = "Break not exercised"

    vat = _section(text, "VAT", ["EPC Rating", "Joint Agent", "Note"])
    if vat:
        if re.search(r"VAT is applicable", vat, re.I):
            lot.vat_status = "APPLICABLE"
        if re.search(r"TOGC available", vat, re.I):
            lot.vat_status = "APPLICABLE - TOGC AVAILABLE"
        if re.search(r"not applicable|no VAT", vat, re.I):
            lot.vat_status = "NOT APPLICABLE"

    planning = _section(text, "Planning", ["Tenancy", "VAT", "EPC Rating", "Joint Agent", "Note"])
    if planning:
        lot.development_potential = True
        if re.search(r"HMO|House in Multiple Occupation|residential", planning, re.I):
            lot.residential_conversion = True

    if re.search(r"Potential for Development", headline, re.I):
        lot.development_potential = True
    if re.search(r"refurbish|refurbishment", text, re.I):
        lot.refurbishment = True
    if re.search(r"secure yard|yard area", text, re.I):
        lot.parking = "Secure yard / parking" if re.search(r"parking", text, re.I) else "Secure yard"
    elif re.search(r"\bparking\b", text, re.I):
        lot.parking = "Parking"

    for a in ds.find_all("a", href=True):
        href = urljoin(lot.url, a.get("href"))
        if "eigpropertyauctions" in href.lower() or "legal-pack" in href.lower():
            lot.legal_pack_url = href
            lot.legal_pack_status = "AVAILABLE"
            break

    if not lot.image_url:
        for img in main.find_all("img"):
            src = img.get("data-src") or img.get("src")
            if not src:
                continue
            low = src.lower()
            if any(x in low for x in ("logo", "icon", "avatar", "placeholder")):
                continue
            lot.image_url = urljoin(lot.url, src)
            break

    lot.description = text[:6000]
    return lot.finalise()


def _direct_exact_pages(targets):
    session = requests.Session()
    session.headers.update(AHL_HEADERS)
    try:
        session.get(URL, timeout=12)
    except Exception:
        pass
    out = {}
    for href, card, lotno in targets:
        try:
            r = session.get(href, headers=AHL_HEADERS, timeout=10, allow_redirects=True)
            if r.ok and len(r.text) > 1200:
                out[href] = BeautifulSoup(r.text, "lxml")
        except Exception:
            pass
        time.sleep(0.18)
    return out


def _browser_exact_pages(targets, already):
    missing = [x for x in targets if x[0] not in already]
    if not missing:
        return already
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=AHL_HEADERS["User-Agent"], locale="en-GB")
            page = context.new_page()
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            for href, card, lotno in missing:
                try:
                    page.goto(href, wait_until="domcontentloaded", timeout=15000)
                    html = page.content()
                    if len(html) > 1200:
                        already[href] = BeautifulSoup(html, "lxml")
                except Exception:
                    pass
            context.close()
            browser.close()
    except Exception:
        pass
    return already


def collect():
    try:
        s = soup(URL, use_browser=False)
        seen, targets = set(), []
        for a in s.find_all("a", href=True):
            href = urljoin(URL, a["href"])
            if "/lot/" not in href or href in seen:
                continue
            seen.add(href)
            card = nearest_card(a, 4200)
            low = card.lower()
            if "sold prior" in low or "withdrawn" in low:
                continue
            if not _ahl_card_is_commercial(card):
                continue
            m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", card, re.I)
            targets.append((href, card, f"Lot {m.group(1)}" if m else None))

        if not targets:
            s = soup(URL, use_browser=True)
            for a in s.find_all("a", href=True):
                href = urljoin(URL, a["href"])
                if "/lot/" not in href or href in seen:
                    continue
                seen.add(href)
                card = nearest_card(a, 4200)
                if not _ahl_card_is_commercial(card):
                    continue
                m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", card, re.I)
                targets.append((href, card, f"Lot {m.group(1)}" if m else None))

        exact = _direct_exact_pages(targets)
        exact = _browser_exact_pages(targets, exact)

        lots = []
        enriched = 0
        fallback = 0
        for href, card, lotno in targets:
            base = _lot_from_card(href, card, lotno)
            ds = exact.get(href)
            if ds is not None and _looks_like_exact(ds, base):
                lots.append(_rich_detail(base, ds))
                enriched += 1
            else:
                lots.append(base)
                fallback += 1

        status = "LIVE" if lots else "FAILED"
        msg = (
            f"Sep 2/3 commercial catalogue candidates {len(targets)}; {len(lots)} published; "
            f"{enriched} exact-page enriched; {fallback} catalogue-card fallback; 0 suppressions"
        )
        return SourceResult(SOURCE, status, lots, msg)
    except Exception as e:
        return SourceResult(SOURCE, "FAILED", [], str(e))
