import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, is_commercial, norm, parse_tenure, parse_vat
from .financials import guide_range, income_facts
from .publication_quality import commercial_decision, asset_text
from .utils import soup, nearest_card, detail_lot, enrich_common_fields, legal_pack

SOURCE = "Pugh / BTG Eddisons"
BASE = "https://www.pugh-auctions.com"
SEARCH = BASE + "/property-search?include-sold=on&order-results=date-desc&style=list"


def _auction_date(text):
    text = norm(text)
    for pat, fmt in ((r"\b(\d{1,2}/\d{1,2}/20\d{2})\b", "%d/%m/%Y"),(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b", "%d %B %Y")):
        m = re.search(pat, text, re.I)
        if not m: continue
        raw = m.group(1) if len(m.groups()) == 1 else " ".join(m.groups())
        try: return datetime.strptime(raw, fmt).date().isoformat()
        except Exception: pass
    return None


def _lot_no(text):
    # An address beginning "15 Percy Street" is not Lot 15.
    text = norm(text); m = re.search(r"\bLot\s+(\d+[A-Z]?)", text, re.I)
    return f"Lot {m.group(1)}" if m else None


def _terminal_status(text):
    low=norm(text).lower()
    if "sold prior" in low: return "SOLD PRIOR"
    if "withdrawn" in low: return "WITHDRAWN"
    if "postponed" in low: return "POSTPONED"
    if re.search(r'\bsold(?:\s+for)?\b', low): return "SOLD"
    return None


def _property_cards(s):
    out = {}
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if "/property/" not in href: continue
        row = a.find_parent('tr')
        if row:
            cells = row.find_all('td', recursive=False)
            number = norm(cells[0].get_text(' ',strip=True)) if cells else ''
            prefix = 'Lot '+number+' ' if re.fullmatch(r'\d+[A-Z]?',number,re.I) else ''
            status = _terminal_status(cells[5].get_text(' ',strip=True)) if len(cells)>5 else None
            card = prefix + ('Status: '+status+' ' if status else '') + norm(row.get_text(' ',strip=True))
        else:
            card = nearest_card(a, 3600) or norm(a.get_text(" ", strip=True))
        if card: out[href] = card
    return out


def _page_targets(s, today):
    out = {}
    for href, card in _property_cards(s).items():
        auction_date = _auction_date(card)
        # Catalogue teasers are incomplete; inspect every current/future lot.
        if not auction_date or auction_date < today: continue
        status = re.search(r'\bStatus:\s*(SOLD PRIOR|WITHDRAWN|POSTPONED|SOLD)\b',card,re.I)
        out[href] = (card, _lot_no(card), auction_date, status.group(1).upper() if status else None)
    return out


def _amount(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try: return float(m.group(1).replace(",", ""))
            except Exception: pass
    return None


def _floor_area_sqft(text):
    """Return the best explicit whole-property area, never a convenient room figure.

    Pugh commonly publishes a precise TOTAL GIA/NIA in square metres followed by the
    authoritative rounded square-foot equivalent in parentheses, while marketing prose
    above may say merely 'just over 1,600 sq ft'. Prefer the labelled total and stated
    imperial equivalent before any rounded prose or component measurement.
    """
    text = text or ""
    paired = re.search(
        r"(?:overall|total)\s+(?:gross\s+internal\s+floor\s+area|net\s+internal\s+floor\s+area|floor\s+area|nia|gia)"
        r"\s*[:\-]?\s*[\d,]+(?:\.\d+)?\s*(?:sq\.?\s*m|sqm|m²)\s*\(\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s*\)",
        text, re.I,
    )
    if paired:
        try:
            value=float(paired.group(1).replace(",", ""))
            if 20 <= value <= 5_000_000: return value
        except Exception: pass

    labelled = (
        r"(?:overall|total)\s+(?:gross\s+internal\s+floor\s+area|net\s+internal\s+floor\s+area|floor\s+area|nia|gia)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"(?:overall|total)(?:\s+(?:floor|internal|gross|net))?\s*(?:area|nia|gia)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    for pat in labelled:
        vals=[]
        for m in re.finditer(pat, text, re.I):
            try:
                value=float(m.group(1).replace(",", ""))
                if 20 <= value <= 5_000_000: vals.append(value)
            except Exception: pass
        if vals: return max(vals)

    # If the authoritative total is only metric, convert it before considering
    # rounded marketing prose such as 'just over 1,600 sq ft'.
    m=re.search(r"(?:overall|total)\s+(?:gross\s+internal\s+floor\s+area|net\s+internal\s+floor\s+area|floor\s+area|nia|gia)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)", text, re.I)
    if m:
        try: return float(m.group(1).replace(",",""))*10.7639
        except Exception: pass

    prose = (
        r"(?:provides?|providing|comprising|extending|extends)\s+(?:just\s+)?(?:over\s+)?(?:approximately\s+|approx\.?\s+|circa\s+)?([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s+(?:of\s+)?(?:accommodation|floor\s*space|space)",
        r"(?:extending|extends)\s+(?:to\s*)?(?:approximately\s+|approx\.?\s+|circa\s+)?([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    for pat in prose:
        vals=[]
        for m in re.finditer(pat, text, re.I):
            try:
                value=float(m.group(1).replace(",", ""))
                if 20 <= value <= 5_000_000: vals.append(value)
            except Exception: pass
        if vals: return max(vals)

    vals=[]
    for m in re.finditer(r"\b([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\b", text, re.I):
        try:
            value=float(m.group(1).replace(",", ""))
            if 20 <= value <= 5_000_000: vals.append(value)
        except Exception: pass
    return max(vals) if vals else None


def _pugh_property_type(text):
    low = " " + norm(text).lower() + " "; commercial = any(x in low for x in ("retail", "shop", "commercial unit", "commercial units", "office", "warehouse", "workshop", "industrial")); residential = bool(re.search(r"\b(?:apartment|apartments|flat|flats|bedsit|bedsits|residential accommodation)\b", low))
    if "mixed use" in low or "mixed-use" in low or (commercial and residential): return "Mixed Use"
    if any(x in low for x in ("industrial", "warehouse", "workshop")): return "Industrial"
    if any(x in low for x in ("retail premises", "retail units", "retail unit", "retail property", " shop ")): return "Retail"
    if "office" in low: return "Office"
    return None


def _apply_pugh_particulars(lot, page_soup):
    if not lot or page_soup is None: return lot
    main = page_soup.find("main") or page_soup; text = norm(main.get_text(" ", strip=True)); lot.description = text[:9000]
    rent = _amount((r"(?:current\s+)?gross income\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",r"combined rental income(?:\s+of)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",r"(?:rental income|annual income|producing|let at|rent of)\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)",r"£\s*([\d,]+(?:\.\d+)?)\s*(?:p\s*/\s*a|p\.?a\.?|pa|per annum)"), text)
    if rent is not None: lot.annual_rent = rent
    sqft = _floor_area_sqft(text)
    if sqft: lot.area_sqft = sqft; lot.area_sqm = sqft / 10.7639
    if re.search(r"\bFRI\b|full repairing and insuring", text, re.I): lot.fri = True
    terms = re.findall(r"\b(\d+(?:\.\d+)?)\s+year\s+FRI\s+lease", text, re.I) or re.findall(r"\b(\d+(?:\.\d+)?)\s+year\s+(?:lease|term)", text, re.I)
    if terms: lot.lease_term = " / ".join(dict.fromkeys(f"{x} years" for x in terms[:3]))
    if re.search(r"no break clauses?|without (?:a )?break", text, re.I): lot.break_clause = "No break clauses stated"
    if re.search(r"personal guarantor|guarantor is secured|guaranteed by", text, re.I): lot.guarantors = "Personal guarantor stated"
    m = re.search(r"tenant in situ\s*\(([^)]+)\)", text, re.I)
    if m: lot.tenant = norm(m.group(1))[:120]
    if re.search(r"(?:nil|nill|peppercorn)\s+rent", text, re.I): lot.annual_rent = None; lot.occupation = "Occupied - nominal/no income"
    elif re.search(r"vacant first and second floors|vacant upper floors|part(?:ly)? vacant", text, re.I) and lot.annual_rent: lot.occupation = "Part let / part vacant"
    elif lot.annual_rent: lot.occupation = "Tenanted"
    elif re.search(r"previously occupied|own occupation|vacant possession|\bvacant\b", text, re.I): lot.occupation = "Vacant"
    if re.search(r"development opportunity|development potential|potential to develop|redevelop", text, re.I): lot.development_potential = True
    if re.search(r"possible conversion|potential.*conversion|conversion opportunity", text, re.I): lot.asset_management = "Conversion / alternative-use potential stated"
    if re.search(r"\b(\d+)\s+parking spaces?\b", text, re.I):
        pm=re.search(r"\b(\d+)\s+parking spaces?\b",text,re.I); lot.parking=f"{pm.group(1)} parking spaces"
    elif re.search(r"secure gated car park|secure car park|rear car park",text,re.I): lot.parking="Car parking stated"
    if re.search(r"reroofed|re-roofed|new roof",text,re.I): lot.refurbishment="Roof works/improvement stated"
    if re.search(r"bedsits?|apartments?|flats?|residential accommodation|residential conversion|convert(?:ed|ing)? to residential", text, re.I) and re.search(r"convert|conversion|develop|upper floors?|apartments?|flats?|bedsits?", text, re.I): lot.residential_conversion = bool(re.search(r"convert|conversion|develop|upper floors?|vacant", text, re.I)) or lot.residential_conversion
    inferred = _pugh_property_type(text)
    if inferred: lot.property_type = inferred
    return lot.finalise()


def _parse_detail(page, href, card='', lotno=None, auction_date=None, card_status=None):
    """Read one Pugh lot, keeping fees and recommended properties out of facts."""
    heading = page.find('h1')
    body = page.select_one('.cms-content')
    if not heading or not body:
        raise ValueError('Pugh property heading/particulars missing')
    header = heading.parent.parent.parent
    header_text = norm(header.get_text(' ',strip=True))
    particulars = norm(body.get_text(' ',strip=True))
    address = norm(heading.get_text(' ',strip=True))
    decision = commercial_decision({'address':address,'description':particulars})
    if decision is False or (decision is None and not is_commercial(asset_text(particulars))):
        return None
    price_label = page.find(string=lambda t:t and norm(t)=='Guide Price')
    price_text = norm(price_label.parent.parent.get_text(' ',strip=True)) if price_label else header_text
    # The price is a sibling of the Guide Price link on Pugh's template.
    if price_label and not re.search(r'£',price_text):
        price_text = norm(price_label.parent.parent.parent.get_text(' ',strip=True))
    guide,upper,raw = guide_range(re.sub(r'\s+to\s+(?=£)', '–', price_text, flags=re.I))
    primary = page.select_one('img[alt="Property image"]')
    lp_url,lp_status = legal_pack(page,href)
    lot = Lot(SOURCE,href,address,lot_number=_lot_no(header_text) or lotno,
              auction_date=_auction_date(header_text) or auction_date,
              guide_price=guide,guide_price_upper=upper,guide_price_text=raw,
              image_url=urljoin(href,primary['src']) if primary and primary.get('src') else None,
              image_is_primary=bool(primary),image_source_url=href,
              tenure=parse_tenure(particulars),vat_status=parse_vat(particulars),
              legal_pack_url=lp_url,legal_pack_status=lp_status,
              status=_terminal_status(header_text) or card_status or 'CURRENT')
    from bs4 import BeautifulSoup
    scoped = BeautifulSoup('<main></main>','lxml')
    scoped.main.append(BeautifulSoup(str(body),'lxml'))
    lot = _apply_pugh_particulars(lot,scoped)
    facts = income_facts(particulars)
    lot.annual_rent = facts.get('annual_rent')
    lot = enrich_common_fields(lot,particulars)
    # Unit 15's floor area is not the total for a portfolio of four units.
    if len(set(re.findall(r'\bNumber\s+(\d+[A-Z]?)\b',particulars,re.I))) > 1 and not re.search(r'\b(?:overall|total)\s+(?:gross|net|floor|area|NIA|GIA)',particulars,re.I):
        lot.area_sqft = lot.area_sqm = None
    return lot.finalise()


def collect():
    try:
        today = date.today().isoformat(); targets = {}; previous_ids = None; pages_seen = 0; future_pages_seen = 0; past_only_streak = 0
        for page in range(1, 81):
            url = SEARCH if page == 1 else SEARCH + f"&page={page}"
            try: s = soup(url, use_browser=False)
            except Exception as exc: print("PUGH_INDEX_FAIL", page, repr(exc)); continue
            pages_seen += 1; cards = _property_cards(s); page_ids = set(cards)
            if page > 1 and page_ids and page_ids == previous_ids: break
            if not page_ids:
                if future_pages_seen: break
                previous_ids = page_ids; continue
            dates = sorted({d for d in (_auction_date(card) for card in cards.values()) if d}); has_future = any(d >= today for d in dates)
            if has_future: future_pages_seen += 1; past_only_streak = 0
            elif dates and max(dates) < today: past_only_streak += 1
            else: past_only_streak = 0
            targets.update(_page_targets(s, today))
            if future_pages_seen and past_only_streak >= 2: break
            previous_ids = page_ids
        if not targets: return SourceResult(SOURCE, "FAILED" if future_pages_seen else "CATALOGUE PENDING", [], f"Pugh future inventory was visible across {future_pages_seen} page(s) but no commercial/mixed-use lots were captured." if future_pages_seen else f"Newest-first Pugh search scanned {pages_seen} page(s); no future catalogue inventory identified.", discovered_count=0)
        lots=[]; failures=0; terminal_count=0; suppressed_noncommercial=0
        def hydrate(item):
            href,(card,lotno,auction_date,card_status)=item
            lot=_parse_detail(soup(href,use_browser=False),href,card,lotno,auction_date,card_status)
            if not lot: return None,card_status
            lifecycle=_terminal_status(lot.status)
            return lot.finalise(),lifecycle
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures={ex.submit(hydrate,item):item[0] for item in targets.items()}
            for f in as_completed(futures):
                try:
                    lot,lifecycle=f.result()
                    if lot and str(lot.auction_date or "")[:10] >= today: lots.append(lot); terminal_count += int(bool(lifecycle))
                    elif lot is None: suppressed_noncommercial += 1
                except Exception as exc: failures+=1; print("PUGH_DETAIL_FAIL",futures[f],repr(exc))
        dedup={}
        for lot in lots: dedup[lot.url or (norm(lot.address).lower(),lot.auction_date)]=lot
        lots=list(dedup.values()); scope_dates=tuple(sorted({str(x.auction_date)[:10] for x in lots if x.auction_date})); status="LIVE" if lots and failures==0 else "DEGRADED" if lots else "FAILED"
        available=sum(1 for x in lots if _terminal_status(x.status) is None and str(x.status or "").upper() not in {"SOLD PRIOR","WITHDRAWN","POSTPONED"})
        return SourceResult(SOURCE,status,lots,f"Newest-first all-future sweep: {pages_seen} page(s); {len(targets)} lots discovered before classification; {available} available and {terminal_count} unavailable commercial/mixed-use lots; {suppressed_noncommercial} noncommercial excluded; {failures} detail failures.",discovered_count=len(targets),expected_count=len(lots) if not failures else None,authoritative_snapshot=False,scope_dates=scope_dates,reconciliation={'catalogue_pages':pages_seen,'discovered_lot_urls':len(targets),'detail_pages_inspected':len(targets)-failures,'commercial_mixed_lots':len(lots),'noncommercial_excluded':suppressed_noncommercial,'detail_failures':failures})
    except Exception as exc: return SourceResult(SOURCE, "FAILED", [], f"Pugh discovery failed: {exc}")
