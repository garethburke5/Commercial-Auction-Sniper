from __future__ import annotations

import re


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _money(value):
    try:
        return f"£{float(value):,.0f}"
    except Exception:
        return None


def _text(row):
    return _norm(" ".join(str(row.get(k) or "") for k in (
        "property_type", "occupation", "desc", "description", "tenant",
        "lease_term", "break_clause", "guarantors", "pitch", "nearby_occupiers",
    )))


def _property_kind(low):
    if "ground rent" in low or "ground rents" in low:
        return "GROUND RENT"
    if any(x in low for x in ("industrial", "warehouse", "workshop", "factory")):
        return "INDUSTRIAL"
    if any(x in low for x in ("public house", " pub ", "drinking establishment")):
        return "PUBLIC HOUSE"
    if any(x in low for x in ("office", "offices")):
        return "OFFICE"
    if any(x in low for x in ("retail", "shop", "high street", "commercial unit")):
        return "RETAIL"
    if any(x in low for x in ("hotel", "guest house", "hospitality")):
        return "HOSPITALITY"
    return "COMMERCIAL"


def _has_upper_development(low):
    return bool(
        re.search(r"vacant (?:first|upper|first and second|upper) floors?", low)
        or ("upper floor" in low and any(x in low for x in ("develop", "conversion", "residential", "bedsit", "flat")))
        or "residential conversion" in low
    )


def _title(row, low):
    rent = row.get("rent") if row.get("rent") is not None else row.get("annual_rent")
    occupation = _norm(row.get("occupation")).lower()
    kind = _property_kind(" " + low + " ")

    if "ground rent" in low or "ground rents" in low:
        return "GROUND RENT INVESTMENT"
    mixed = any(x in low for x in ("mixed use", "mixed-use", "retail and residential", "shop and flat", "shop with flat"))
    upper_dev = _has_upper_development(low)
    development = upper_dev or any(x in low for x in ("development opportunity", "redevelopment opportunity", "development potential"))
    vacant = "vacant" in low or occupation.startswith("vacant")
    nominal = bool(re.search(r"(?:nil|nill|peppercorn)\s+rent", low))

    if mixed and development and rent:
        return "MIXED-USE INVESTMENT + DEVELOPMENT"
    if mixed and rent:
        return "MIXED-USE INVESTMENT"
    if mixed:
        return "MIXED-USE OPPORTUNITY"
    if kind == "RETAIL" and development and rent:
        return "RETAIL INVESTMENT + UPPER-FLOOR DEVELOPMENT"
    if kind == "RETAIL" and development:
        return "RETAIL + DEVELOPMENT OPPORTUNITY"
    if nominal:
        return f"{kind} OPPORTUNITY · NOMINAL INCOME"
    if rent:
        return f"{kind} INVESTMENT"
    if vacant:
        return f"VACANT {kind} OPPORTUNITY"
    if development:
        return f"{kind} DEVELOPMENT OPPORTUNITY"
    return f"{kind} OPPORTUNITY"


def _extract_units(low):
    m = re.search(r"comprising\s+(two|three|four|five|\d+)\s+adjoining\s+ground floor retail units", low)
    if m:
        return f"{m.group(1).title()} adjoining ground-floor retail units"
    m = re.search(r"comprising\s+(two|three|four|five|\d+)\s+(?:ground floor )?retail units", low)
    if m:
        return f"{m.group(1).title()} retail units"
    return None


def _extract_former_use(text):
    m = re.search(r"formerly\s+(?:an?|the)?\s*([^.;]{2,55}?)(?=\s+(?:extending|comprising|with|and|benefitting)|[.;])", text, re.I)
    if m:
        return "Former " + _norm(m.group(1)).strip(" ,-")
    return None


def _extract_area(row, text):
    sqft = row.get("area_sqft")
    if sqft:
        try:
            return f"{float(sqft):,.0f} sq ft"
        except Exception:
            pass
    patterns = (
        r"(?:extending|extends|approximately|approx\.?|circa|total(?: floor)? area(?: of)?)\s*(?:to\s*)?([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"\b([\d,]+)\s*(?:sq\.?\s*ft|sqft|ft²)\b",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                v = float(m.group(1).replace(",", ""))
                if 100 <= v <= 2_000_000:
                    return f"{v:,.0f} sq ft"
            except Exception:
                pass
    return None


def _lease_highlight(row, text):
    parts = []
    if row.get("lease_term"):
        parts.append(_norm(row["lease_term"]))
    if row.get("fri") is True or re.search(r"\bFRI\b|full repairing and insuring", text, re.I):
        parts.append("FRI")
    if re.search(r"no break clauses?|without (?:a )?break", text, re.I):
        parts.append("no break")
    if parts:
        return "Lease: " + " · ".join(dict.fromkeys(parts))
    return None


def build_opportunity_summary(row):
    """Return (headline, highlights) using only evidence already captured from the listing.

    The output is deliberately compact for the card surface. It never invents a tenant,
    lease term, area or development angle; every highlight must be evidenced in the row.
    """
    text = _text(row)
    low = text.lower()
    headline = _title(row, low)
    highlights = []

    rent = row.get("rent") if row.get("rent") is not None else row.get("annual_rent")
    if re.search(r"(?:nil|nill|peppercorn)\s+rent", low):
        highlights.append("Tenant in situ · nil rent")

    units = _extract_units(low)
    if units:
        if "vacant first and second floors" in low or "vacant upper floors" in low:
            units += " + vacant upper floors"
        highlights.append(units)

    area = _extract_area(row, text)
    if area:
        highlights.append(area)

    former = _extract_former_use(text)
    if former:
        highlights.append(former)

    tenant = _norm(row.get("tenant"))
    if tenant:
        highlights.append("Tenant: " + tenant[:70])

    lease = _lease_highlight(row, text)
    if lease:
        highlights.append(lease)

    if _has_upper_development(low):
        m = re.search(r"(?:previously|formerly)\s+(?:been\s+)?utili[sz]ed as\s+(\d+)\s+bedsits", low)
        if m:
            highlights.append(f"Upper floors formerly {m.group(1)} bedsits · residential potential")
        else:
            highlights.append("Upper-floor residential/development potential")

    if re.search(r"rear loading (?:bay|access)", low):
        highlights.append("Rear loading bay")
    if "large frontage" in low or "substantial frontage" in low:
        highlights.append("Large frontage")

    # Keep the surface concise and unique. Financial metrics already have their own boxes.
    unique = []
    for item in highlights:
        item = _norm(item)
        if item and item.lower() not in {x.lower() for x in unique}:
            unique.append(item)
    return headline, unique[:4]
