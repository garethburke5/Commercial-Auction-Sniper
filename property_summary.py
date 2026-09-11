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


def _has_planning_consent(low):
    return bool(
        re.search(r"planning permission (?:has been |was )?granted", low)
        or re.search(r"(?:full|outline) planning permission", low)
        or re.search(r"benefits? from (?:an? )?(?:existing )?planning (?:permission|consent)", low)
        or re.search(r"\bconsented\b", low)
    )


def _is_rooftop_development(low):
    return bool(
        re.search(r"\b(?:roof ?space|airspace|rooftop)\b", low)
        and (
            _has_planning_consent(low)
            or any(x in low for x in ("development opportunity", "development potential", "additional storey", "extra storey"))
        )
    )


def _has_conversion_potential(low):
    return bool(
        any(x in low for x in (
            "development opportunity", "redevelopment opportunity", "development potential",
            "residential conversion", "conversion potential", "alternative use",
            "alternative uses", "potential for reconfiguration", "potential for conversion",
            "scope for reconfiguration", "scope for conversion",
        ))
        or re.search(r"potential for (?:permitted development to )?convert", low)
        or re.search(r"potential for .*?(?:hmo|house of multiple occupation|self-contained residential units|boutique hotel)", low)
    )


def _is_ground_rent_investment(row, low, development):
    """Only classify the asset itself as ground rent, never an incidental lease cost."""
    primary = _norm(row.get("property_type")).lower()
    opening = low[:260]
    explicit_primary = bool(re.search(r"\bground rents? investment\b|\bground rent portfolio\b", primary))
    explicit_headline = bool(re.search(r"\b(?:freehold|residential|commercial)?\s*ground rents? investment\b|\bground rent portfolio\b", opening))
    nominal = bool(
        re.search(r"(?:peppercorn|nil|nill|nominal)(?: annual)? (?:ground )?rent", low)
        or re.search(r"ground rent.{0,45}(?:peppercorn|nil|nill|nominal)", low)
    )
    operative_interest = bool(
        development
        or _is_rooftop_development(low)
        or re.search(r"\b(?:roof ?space|airspace)\b", low)
        or "vacant possession" in low
    )
    if nominal and operative_interest:
        return False
    if development:
        return False
    return explicit_primary or explicit_headline


def _title(row, low):
    rent = row.get("rent") if row.get("rent") is not None else row.get("annual_rent")
    occupation = _norm(row.get("occupation")).lower()
    kind = _property_kind(" " + low + " ")
    mixed = any(x in low for x in (
        "mixed use", "mixed-use", "mixed commercial/residential", "mixed commercial / residential",
        "mixed residential and commercial", "retail and residential", "shop and flat", "shop with flat",
    ))
    upper_dev = _has_upper_development(low)
    rooftop_dev = _is_rooftop_development(low)
    consented = _has_planning_consent(low)
    development = rooftop_dev or upper_dev or _has_conversion_potential(low)
    vacant = "vacant" in low or occupation.startswith("vacant")
    part_vacant = "part vacant" in occupation or "part let" in occupation or bool(
        rent and re.search(r"\b(?:plus\s+)?[\d,]+\s*sq\.?\s*ft[^.]{0,45}\bvacant\b", low)
    )
    nominal = bool(re.search(r"(?:nil|nill|peppercorn)\s+rent", low))

    if rooftop_dev and consented:
        return "CONSENTED ROOFTOP RESIDENTIAL DEVELOPMENT"
    if consented and development and any(x in low for x in ("residential", "flat", "dwelling")):
        return "CONSENTED RESIDENTIAL DEVELOPMENT"
    if mixed and development and rent:
        return "MIXED-USE INVESTMENT + DEVELOPMENT"
    if mixed and development and vacant:
        return "VACANT MIXED-USE + CONVERSION OPPORTUNITY"
    if mixed and development:
        return "MIXED-USE + CONVERSION OPPORTUNITY"
    if mixed and rent:
        return "MIXED-USE INVESTMENT"
    if mixed:
        return "MIXED-USE OPPORTUNITY"
    if kind == "RETAIL" and development and rent:
        return "RETAIL INVESTMENT + UPPER-FLOOR DEVELOPMENT"
    if kind == "RETAIL" and development:
        return "RETAIL + DEVELOPMENT OPPORTUNITY"
    if _is_ground_rent_investment(row, low, development):
        return "GROUND RENT INVESTMENT"
    if nominal:
        return f"{kind} OPPORTUNITY · NOMINAL INCOME"
    if kind == "OFFICE" and rent and part_vacant:
        return "PART-LET OFFICE INVESTMENT + VACANCY"
    if kind == "OFFICE" and development and vacant:
        return "VACANT OFFICE + RESIDENTIAL CONVERSION OPPORTUNITY"
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


def _mixed_use_composition(text, low):
    if not any(x in low for x in (
        "mixed use", "mixed-use", "mixed commercial/residential", "mixed commercial / residential",
        "mixed residential and commercial", "retail and residential", "shop and flat", "shop with flat",
    )):
        return None
    if "ground floor retail" in low and "maisonette" in low:
        beds = re.search(r"Bedrooms\s*x\s*(\d+)", text, re.I)
        baths = re.search(r"Bathrooms\s*x\s*(\d+)", text, re.I)
        detail = "Ground-floor retail + upper-floor maisonette"
        if beds:
            detail += f" · {beds.group(1)} beds"
        if baths:
            detail += f" / {baths.group(1)} baths"
        return detail
    if "ground floor retail" in low and any(x in low for x in ("flat", "residential accommodation", "upper floors")):
        return "Ground-floor retail + residential upper parts"
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
    text = _text(row)
    low = text.lower()
    headline = _title(row, low)
    highlights = []

    if re.search(r"(?:nil|nill|peppercorn)\s+rent", low):
        highlights.append("Tenant in situ · nil rent")

    composition = _mixed_use_composition(text, low)
    if composition:
        highlights.append(composition)

    units = _extract_units(low)
    if units:
        if "vacant first and second floors" in low or "vacant upper floors" in low:
            units += " + vacant upper floors"
        highlights.append(units)

    area = _extract_area(row, text)
    if area:
        highlights.append(area)

    vacancy = re.search(r"([\d,]+)\s*sq\.?\s*ft[^.]{0,55}\b(?:currently\s+)?vacant\b|(?:plus\s+)([\d,]+)\s*sq\.?\s*ft\s+vacant", text, re.I)
    if vacancy:
        value = vacancy.group(1) or vacancy.group(2)
        highlights.append(f"{value} sq ft vacant / reletting opportunity")

    former = _extract_former_use(text)
    if former:
        highlights.append(former)

    tenant = _norm(row.get("tenant"))
    if tenant:
        highlights.append("Tenant: " + tenant[:70])

    lease = _lease_highlight(row, text)
    if lease:
        highlights.append(lease)

    parking = _norm(row.get("parking"))
    if parking:
        highlights.append(parking[:90])

    pitch = _norm(row.get("pitch"))
    if pitch:
        highlights.append(pitch[:120])

    if _has_upper_development(low):
        m = re.search(r"(?:previously|formerly)\s+(?:been\s+)?utili[sz]ed as\s+(\d+)\s+bedsits", low)
        if m:
            highlights.append(f"Upper floors formerly {m.group(1)} bedsits · residential potential")
        else:
            highlights.append("Upper-floor residential/development potential")

    if _has_conversion_potential(low):
        if any(x in low for x in ("hmo", "house of multiple occupation", "self-contained residential units", "boutique hotel")):
            highlights.append("Reconfiguration / residential / HMO / alternative-use potential STC")
        else:
            highlights.append("Reconfiguration / conversion / alternative-use potential STC")

    if "basement accommodation" in low or "basement room" in low:
        highlights.append("Basement accommodation")
    if "rear yard" in low or "rear courtyard" in low or "courtyard garden" in low:
        highlights.append("Rear yard / courtyard")
    if "roof terrace" in low:
        highlights.append("Roof terrace")
    if re.search(r"rear loading (?:bay|access)", low):
        highlights.append("Rear loading bay")
    if "large frontage" in low or "substantial frontage" in low:
        highlights.append("Large frontage")

    unique = []
    for item in highlights:
        item = _norm(item)
        if item and item.lower() not in {x.lower() for x in unique}:
            unique.append(item)
    return headline, unique[:4]
