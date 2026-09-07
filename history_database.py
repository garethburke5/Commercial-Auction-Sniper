from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b", re.I)
UNIT_WORDS = {"unit", "units", "flat", "flats", "suite", "shop", "shops", "floor", "floors", "ground", "first", "second", "third"}
NOISE_WORDS = {
    "the", "and", "at", "of", "property", "premises", "freehold", "leasehold",
    "road", "rd", "street", "st", "avenue", "ave", "lane", "ln", "drive", "dr",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def postcode(address):
    m = POSTCODE_RE.search(_text(address).upper())
    return re.sub(r"\s+", "", m.group(1).upper()) if m else None


def normalize_address(address):
    value = _text(address).lower()
    value = POSTCODE_RE.sub(" ", value)
    value = value.replace("&", " and ")
    value = re.sub(r"\b(?:street)\b", " st ", value)
    value = re.sub(r"\b(?:road)\b", " rd ", value)
    value = re.sub(r"\b(?:avenue)\b", " ave ", value)
    value = re.sub(r"\b(?:lane)\b", " ln ", value)
    value = re.sub(r"\b(?:drive)\b", " dr ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return _text(value)


def building_tokens(address):
    value = normalize_address(address)
    # Keep numeric building identifiers including 33a and ranges such as 54-58.
    raw = re.findall(r"\b\d+[a-z]?\b", value)
    return set(raw[:6])


def _street_tokens(address):
    toks = []
    for token in normalize_address(address).split():
        if token in NOISE_WORDS or token in UNIT_WORDS or re.fullmatch(r"\d+[a-z]?", token):
            continue
        toks.append(token)
    return toks


def match_score(address_a, address_b):
    """Return 0..1 confidence that two auction address strings are the same asset.

    Postcode and building identifiers carry most weight. The textual score is only a
    supporting signal so neighbouring properties are not silently merged.
    """
    a, b = _text(address_a), _text(address_b)
    if not a or not b:
        return 0.0
    pa, pb = postcode(a), postcode(b)
    score = 0.0
    if pa and pb:
        if pa != pb:
            return 0.0
        score += 0.55
    elif pa or pb:
        score += 0.05

    ba, bb = building_tokens(a), building_tokens(b)
    if ba and bb:
        overlap = len(ba & bb) / max(1, min(len(ba), len(bb)))
        if overlap == 0 and pa and pb:
            # Same postcode but clearly different numbered premises.
            return min(score, 0.55)
        score += 0.25 * overlap

    sa, sb = " ".join(_street_tokens(a)), " ".join(_street_tokens(b))
    if sa and sb:
        score += 0.20 * SequenceMatcher(None, sa, sb).ratio()
    return round(min(score, 1.0), 4)


def _property_id(address):
    pc = postcode(address) or "NOPOSTCODE"
    seed = f"{pc}|{normalize_address(address)}"
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def _event_id(item):
    # Source URL is normally the strongest stable identity. Auction date/lot number
    # protect against auctioneers reusing generic catalogue URLs.
    seed = "|".join(
        _text(item.get(k)).lower()
        for k in ("source", "url", "auction_date", "lot_number")
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:24]


def empty_database():
    return {
        "schema_version": 1,
        "generated_at": None,
        "properties": [],
        "auction_events": [],
        "stats": {},
    }


def load_database(path):
    p = Path(path)
    if not p.exists():
        return empty_database()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return empty_database()
        data.setdefault("schema_version", 1)
        data.setdefault("properties", [])
        data.setdefault("auction_events", [])
        data.setdefault("stats", {})
        return data
    except Exception:
        return empty_database()


def _find_property(properties, address, threshold=0.78):
    best = None
    best_score = 0.0
    for prop in properties:
        variants = prop.get("address_variants") or [prop.get("canonical_address")]
        score = max((match_score(address, v) for v in variants if v), default=0.0)
        if score > best_score:
            best, best_score = prop, score
    return (best, best_score) if best_score >= threshold else (None, best_score)


def _observation(item, observed_at):
    return {
        "observed_at": observed_at,
        "status": _text(item.get("status")) or None,
        "guide_price": item.get("guide_price"),
        "annual_rent": item.get("annual_rent"),
        "gross_yield": item.get("gross_yield"),
        "tenure": item.get("tenure"),
        "tenant": item.get("tenant"),
        "lease_term": item.get("lease_term"),
        "occupation": item.get("occupation"),
    }


def _material_observation_changed(previous, current):
    keys = ("status", "guide_price", "annual_rent", "gross_yield", "tenure", "tenant", "lease_term", "occupation")
    return any(previous.get(k) != current.get(k) for k in keys)


def update_history_database(items, path="data/property_history.json", observed_at=None):
    """Append current/archive auction facts into the permanent historical database.

    Existing events are updated, never discarded. Material status/fact changes become
    observations, preserving transitions such as CURRENT -> SOLD PRIOR.
    """
    observed_at = observed_at or _now()
    db = load_database(path)
    properties = db["properties"]
    events = db["auction_events"]
    events_by_id = {e.get("event_id"): e for e in events if e.get("event_id")}

    added_events = updated_events = added_properties = 0
    for raw in items:
        item = dict(raw or {})
        address = _text(item.get("address"))
        if not address or not _text(item.get("source")) or not _text(item.get("url")):
            continue

        prop, confidence = _find_property(properties, address)
        if prop is None:
            pid = _property_id(address)
            # Hash collisions are extraordinarily unlikely; still protect against one.
            existing_ids = {p.get("property_id") for p in properties}
            if pid in existing_ids:
                pid = hashlib.sha1(f"{pid}|{address}".encode()).hexdigest()[:20]
            prop = {
                "property_id": pid,
                "canonical_address": address,
                "postcode": postcode(address),
                "address_variants": [address],
                "first_seen": observed_at,
                "last_seen": observed_at,
                "auction_event_ids": [],
            }
            properties.append(prop)
            added_properties += 1
            confidence = 1.0
        else:
            prop["last_seen"] = observed_at
            variants = prop.setdefault("address_variants", [])
            if address not in variants:
                variants.append(address)

        eid = _event_id(item)
        event = events_by_id.get(eid)
        evidence = {
            "listing_url": _text(item.get("url")) or None,
            "legal_pack_url": _text(item.get("legal_pack_url")) or None,
            "image_url": _text(item.get("image_url")) or None,
            "source_id": _text(item.get("source_id")) or None,
        }
        current_obs = _observation(item, observed_at)

        if event is None:
            event = {
                "event_id": eid,
                "property_id": prop["property_id"],
                "match_confidence": confidence,
                "source": _text(item.get("source")),
                "auction_date": _text(item.get("auction_date")) or None,
                "lot_number": _text(item.get("lot_number")) or None,
                "address_as_published": address,
                "status": current_obs["status"],
                "guide_price": item.get("guide_price"),
                "annual_rent": item.get("annual_rent"),
                "gross_yield": item.get("gross_yield"),
                "tenure": item.get("tenure"),
                "property_type": item.get("property_type"),
                "tenant": item.get("tenant"),
                "lease_term": item.get("lease_term"),
                "lease_start": item.get("lease_start"),
                "lease_expiry": item.get("lease_expiry"),
                "occupation": item.get("occupation"),
                "area_sqft": item.get("area_sqft"),
                "description": item.get("description"),
                "source_evidence": evidence,
                "first_seen": observed_at,
                "last_seen": observed_at,
                "observations": [current_obs],
            }
            events.append(event)
            events_by_id[eid] = event
            added_events += 1
        else:
            event["last_seen"] = observed_at
            # Preserve the latest explicit facts while never replacing a fact with blank.
            for key in (
                "status", "guide_price", "annual_rent", "gross_yield", "tenure", "property_type",
                "tenant", "lease_term", "lease_start", "lease_expiry", "occupation", "area_sqft", "description",
            ):
                value = current_obs.get(key) if key in current_obs else item.get(key)
                if value not in (None, "", "UNKNOWN", "NOT FOUND"):
                    event[key] = value
            ev = event.setdefault("source_evidence", {})
            for key, value in evidence.items():
                if value:
                    ev[key] = value
            observations = event.setdefault("observations", [])
            if not observations or _material_observation_changed(observations[-1], current_obs):
                observations.append(current_obs)
            updated_events += 1

        event_ids = prop.setdefault("auction_event_ids", [])
        if eid not in event_ids:
            event_ids.append(eid)

    db["generated_at"] = observed_at
    db["stats"] = {
        "property_count": len(properties),
        "auction_event_count": len(events),
        "sold_prior_count": sum(1 for e in events if _text(e.get("status")).upper() == "SOLD PRIOR"),
        "events_with_guide": sum(1 for e in events if e.get("guide_price") is not None),
        "events_with_source_url": sum(1 for e in events if (e.get("source_evidence") or {}).get("listing_url")),
        "added_properties_last_run": added_properties,
        "added_events_last_run": added_events,
        "updated_events_last_run": updated_events,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    return db
