"""Lifecycle-safe Clive Emson collector.

Clive Emson's dedicated commercial catalogue can mark a lot Sold Prior, Withdrawn
or Postponed before the auction. Those records must remain in Auction Sniper's
history even though they must not remain on the live board.
"""
from __future__ import annotations

import re
from datetime import datetime

from .core import SourceResult, Lot, norm, parse_guide, parse_tenure, parse_vat
from .utils import soup, image_from_soup, legal_pack
from . import clive_emson as base

SOURCE = base.SOURCE


def _terminal_status(text):
    value = norm(text)
    if re.search(r"\bSold\s*Prior\b|\bSoldPrior\b", value, re.I): return "SOLD PRIOR"
    if re.search(r"\bWithdrawn(?:\s+Prior)?\b|\bLot\s+Withdrawn\b", value, re.I): return "WITHDRAWN"
    if re.search(r"\bPostponed\b", value, re.I): return "POSTPONED"
    return None


def _clive_facts(text, headline=""):
    """Extract decision-useful facts that Clive Emson publishes explicitly."""
    t = norm(text or "")
    head = norm(headline or "")
    facts = {}

    if re.search(r"mixed residential and commercial|mixed commercial/residential|mixed[- ]use", t, re.I):
        facts["property_type"] = "Mixed Use"
    elif re.search(r"\bpublic house\b|\bfreehouse\b", head, re.I):
        facts["property_type"] = "Public House"
    elif re.search(r"\brestaurant\b", head, re.I):
        facts["property_type"] = "Restaurant"
    elif re.search(r"\boffices?\b", head, re.I) or re.search(r"previously been used as offices", t, re.I):
        facts["property_type"] = "Office"
    elif re.search(r"ground floor corner unit comprises a retail shop|\bretail shop\b|\bretail accommodation\b", t, re.I):
        facts["property_type"] = "Retail"
    elif re.search(r"\bretail\b|\bshop\b", head, re.I):
        facts["property_type"] = "Retail"

    # The interest being sold wins over subordinate lease references in the body.
    if re.search(r"\bTenure\s+Share of Freehold\b|\bshare of freehold\b", t, re.I):
        facts["tenure"] = "Share of Freehold"
    elif re.search(r"\bFreehold with (?:Part )?Vacant Possession\b|\bfreehold building\b|\bfreehold property\b", t, re.I):
        facts["tenure"] = "Freehold"

    areas = [float(x.replace(",", "")) for x in re.findall(r"Total Floor Area\s*([\d,]+(?:\.\d+)?)\s*sq\.?m\.?", t, re.I)]
    if areas:
        facts["area_sqm"] = round(sum(areas), 2)
        facts["area_sqft"] = round(sum(areas) * 10.7639, 1)

    epcs = re.findall(r"EPC Rating\s*([A-G])\s*\(\s*(\d{1,3})\s*\)", t, re.I)
    if epcs:
        facts["epc"] = " / ".join(dict.fromkeys(f"{a.upper()} ({n})" for a, n in epcs))

    residential = bool(re.search(
        r"residential conversion|convert .*?residential|single residential dwelling|"
        r"house of multiple occupation|\bHMO\b|self-contained residential units|"
        r"potential for reconfiguration, conversion or alternative uses",
        t, re.I,
    ))
    if residential:
        facts["residential_conversion"] = True
        facts["development_potential"] = True
    if re.search(r"subject to all necessary consents|subject to .*?consents", t, re.I):
        facts["development_potential"] = True

    # Explicit possession wording has priority. This catches trading businesses sold VP.
    has_vacant = bool(re.search(r"\bvacant(?: possession)?\b|\bcurrently vacant\b", t, re.I))
    has_let = bool(re.search(
        r"\bcurrently (?:part )?let at\b|\bseparately let\b|\blet under the terms\b|"
        r"\blet on (?:a|the)\b|\blet to\b|\blicen[cs]e agreement at\b|\bcurrent rental of\b",
        t, re.I,
    ))
    if "part vacant possession" in t.lower() or (has_vacant and has_let):
        facts["occupation"] = "Part Vacant / Part Let"
    elif re.search(r"\b(?:Freehold|Leasehold) with Vacant Possession\b", t, re.I) or (has_vacant and not has_let):
        facts["occupation"] = "Vacant"
    elif has_let:
        facts["occupation"] = "Let"

    m = re.search(r"commercial lease expiring\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})", t, re.I)
    if m:
        facts["lease_expiry"] = norm(m.group(1))
    m = re.search(r"Remainder of a\s+(\d+)\s*[- ]year lease from\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})", t, re.I)
    if m:
        facts["lease_term"] = f"{m.group(1)} years"
        facts["lease_start"] = norm(m.group(2))

    ground = re.search(r"ground rent(?:al)? of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)", t, re.I)
    if ground:
        facts["ground_rent"] = float(ground.group(1).replace(",", ""))

    highlights = []
    if re.search(r"basement has separate access|basement \(separate access\)|direct rear access into the basement", t, re.I): highlights.append("Basement with separate access")
    if re.search(r"courtyard garden|rear courtyard|yard to rear", t, re.I): highlights.append("Rear courtyard / yard")
    if re.search(r"roof terrace", t, re.I): highlights.append("Roof terrace")
    if re.search(r"old town location|adjacent to .*?old town", t, re.I): highlights.append("Old Town location")
    if re.search(r"close to seafront|short distance of the seafront", t, re.I): highlights.append("Close to seafront")
    if re.search(r"main roof has been replaced within the last 12 months", t, re.I): highlights.append("Main roof replaced within last 12 months")
    if re.search(r"requires significant repair|significant upgrading and refurbishment|state of disrepair", t, re.I):
        facts["refurbishment"] = "Heavy refurbishment / significant repair"
        highlights.append("Significant repair / refurbishment required")
    if re.search(r"listed building consent|\blisted building\b", t, re.I):
        facts["listed_status"] = "Listed / listed-building consent referenced"
        highlights.append("Listed-building considerations")
    if re.search(r"popular village location|centre of yarmouth", t, re.I): highlights.append("Central Yarmouth / popular village pitch")
    if re.search(r"wightlink car ferry terminal|significant tourist footfall", t, re.I): highlights.append("Wightlink ferry / significant tourist footfall")
    if re.search(r"share of freehold transferrable on completion", t, re.I): highlights.append("Share of freehold transfers on completion")
    if re.search(r"\bNil Reserve\b", t, re.I): highlights.append("NIL RESERVE")
    if highlights: facts["pitch"] = " · ".join(highlights)
    return facts


def _parse_detail(url, seed, auction_date):
    page = soup(url, use_browser=False)
    text = norm(page.get_text(" ", strip=True))
    mcat = re.search(r"\bCategory\s+([^#]+?)(?:\s+Tenure\b|\s+Bedrooms\b|\s+Bathrooms\b|\s+Key Features\b)", text, re.I)
    category = norm(mcat.group(1)) if mcat else ""
    cat_low = category.lower()
    if category and not any(x in cat_low for x in ("commercial", "mixed", "industrial", "retail", "office", "leisure", "business")):
        return None

    h1 = page.find("h1")
    h1_text = norm(h1.get_text(" ", strip=True)) if h1 else ""
    lot_number = None
    if h1:
        ml = re.search(r"Lot\s+(\d+[A-Z]?)", h1_text, re.I)
        if ml: lot_number = "Lot " + ml.group(1)
    if not lot_number:
        ml = re.search(r"LOT\s+(\d+[A-Z]?)", seed, re.I)
        lot_number = "Lot " + ml.group(1) if ml else None

    h2 = page.find("h2")
    address = norm(h2.get_text(" ", strip=True)) if h2 else (seed or url)
    mdate = re.search(r"Auction (?:Ends|Date):\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if mdate: auction_date = datetime.strptime(" ".join(mdate.groups()), "%d %B %Y").date().isoformat()

    lp_url, lp_status = legal_pack(page, url)
    lifecycle = _terminal_status(seed + " " + text) or "CURRENT"
    facts = _clive_facts(text, h1_text)
    guide = parse_guide(text) or parse_guide(seed)
    annual_rent = base._parse_passing_rent(text, guide_price=guide)
    # Ground rents/reversionary sums are not occupational rent and must not drive GIY.
    if facts.get("occupation") == "Vacant" and not re.search(r"\bcurrently (?:part )?let at\b", text, re.I):
        annual_rent = None

    description = text[:7000]
    if re.search(r"\bNil Reserve\b", text, re.I) and "NIL RESERVE" not in description:
        description = "NIL RESERVE. " + description

    return Lot(
        source=SOURCE, url=url, address=address, lot_number=lot_number, auction_date=auction_date,
        image_url=image_from_soup(page, url), guide_price=guide, annual_rent=annual_rent,
        tenure=facts.get("tenure") or parse_tenure(text), vat_status=parse_vat(text),
        legal_pack_status=lp_status, legal_pack_url=lp_url, status=lifecycle, description=description,
        property_type=facts.get("property_type") or category or "Commercial / Mixed Use",
        occupation=facts.get("occupation"), area_sqft=facts.get("area_sqft"), area_sqm=facts.get("area_sqm"),
        epc=facts.get("epc"), lease_term=facts.get("lease_term"), lease_start=facts.get("lease_start"),
        lease_expiry=facts.get("lease_expiry"), development_potential=facts.get("development_potential"),
        residential_conversion=facts.get("residential_conversion"), refurbishment=facts.get("refurbishment"),
        listed_status=facts.get("listed_status"), ground_rent=facts.get("ground_rent"), pitch=facts.get("pitch"),
    ).finalise()


def collect():
    try:
        auction_id, auction_date = base._discover_current_auction()
        links = base._candidate_links(auction_id)
        if not links:
            return SourceResult(SOURCE, "FAILED", [], f"Current auction {auction_id} discovered but commercial feed exposed no matching lots.", expected_count=None, discovered_count=0, authoritative_snapshot=False, scope_dates=(auction_date,) if auction_date else ())
        lots = []; failures = 0; rejected = 0; terminal_count = 0
        for href, seed in links.items():
            try: lot = _parse_detail(href, seed, auction_date)
            except Exception as exc:
                failures += 1; print("CLIVE_EMSON_LIFECYCLE_DETAIL_FAIL", href, repr(exc)); continue
            if lot:
                lots.append(lot); terminal_count += int(str(lot.status).upper() != "CURRENT")
            else: rejected += 1
        expected = len(links); complete = failures == 0 and rejected == 0 and len(lots) == expected
        status = "LIVE" if complete else "DEGRADED" if lots else "FAILED"; available = len(lots) - terminal_count
        return SourceResult(SOURCE, status, lots, f"Dynamic auction {auction_id}: {expected} dedicated commercial links; {available} available; {terminal_count} sold-prior/withdrawn/postponed retained as history; {rejected} non-commercial rejects; {failures} detail failures.", expected_count=expected, discovered_count=expected, authoritative_snapshot=complete, scope_dates=(auction_date,) if auction_date else ())
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Clive Emson lifecycle-safe discovery failed: {exc}")
