"""Bank retained TW Gaze land and property catalogues and exact result rows.

The retained PDFs are immutable first-party catalogue evidence exposed through
the auctioneer's property-marketing route.  Rows are admitted only from an
explicit, reviewed lot inventory after the downloaded PDF proves the exact
event date, lot number, address and guide.  Later TW Gaze brochures can enrich
an exact catalogue row with a published result, but never supply an assumed
auction date.  The separate March 2018 result event is verified against TW
Gaze's own event page.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from io import BytesIO
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus


SOURCE = "TW Gaze"
SLUG = "tw-gaze"
OPERATOR = "TWG (1857) LTD"
COMPANY_NUMBER = "08965732"
HEADERS = {"User-Agent": "Commercial-Auction-Sniper/1.0 (+historical lot research)"}
RESULT_URL = (
    "https://www.twgaze.co.uk/auctions/catalogues-and-auctions/"
    "httpsauctions-twgaze-co-ukauction-results/land-and-property-auction-3/print/"
)
RESULT_FALLBACK_URL = RESULT_URL.removesuffix("print/")
NEXT_URL = (
    "https://www.twgaze.co.uk/assets/Uploads/"
    "NEW-March-2023-Land-and-Property-Auction-Brochure.pdf"
)
NEXT_TARGET = (
    "Inventory and bank every individual lot in TW Gaze's retained 15 March 2023 "
    f"Land & Property Auction brochure at {NEXT_URL}; preserve the first-party PDF, "
    "reconcile any result pages by exact event/lot/address, and continue through adjacent "
    "TW Gaze brochures. Separately recover the exact events for the still-unmatched Hopton "
    "and Kenninghall retrospective result rows. Keep national completeness false."
)


def lot(number, address, guide, guide_high=None, *, sale=None, description=None):
    return {
        "lot_number": str(number),
        "address": address,
        "guide_price": guide,
        "guide_price_high": guide_high,
        "sale_price": sale,
        "description": description,
    }


CATALOGUES = (
    {
        "date": "2018-10-04",
        "url": "https://media.onthemarket.com/properties/5508313/673160328/document-0.pdf",
        "lots": (
            lot(1, "Town Farm Barn, Garboldisham Road, East Harling, Norwich, Norfolk NR16 2PU", 200000, 250000),
            lot(2, "Town Farm Cottage, Garboldisham Road, East Harling, Norwich, Norfolk NR16 2PU", 140000, 160000),
            lot(3, "Rushes Cottages, Harling Road, North Lopham, Diss, Norfolk IP22 2NQ", 80000, 120000, sale=226000),
            lot(4, "Methodist Chapel, High Road, Bressingham, Diss, Norfolk IP22 2AT", 100000, 120000),
            lot(5, "The Old Post Office, The Street, Tibenham, Norwich, Norfolk NR16 1AP", 180000, 210000),
            lot(6, "Land off Vicarage Lane, Bramford, Ipswich, Suffolk IP8 4AE", 30000, 40000, sale=126000),
            lot(7, "Southleigh, Ashfield Road, Norton, Bury St Edmunds, Suffolk IP31 3NN", 400000, 450000),
        ),
    },
    {
        "date": "2019-09-12",
        "url": "https://media.onthemarket.com/properties/7407772/1113285375/document-0.pdf",
        "lots": (
            lot(1, "Majors Farm, Yaxley Road, Eye, Suffolk IP23 7HG", 300000, 350000),
            lot(2, "Land at Lower Road, Rockland St Mary, Norfolk", 40000, 60000),
            lot(3, "Land north of Low Common Road, Bunwell, Norfolk NR16 1SS", 30000, 40000, sale=88000),
            lot(4, "Marsh Land at Costessey, Norfolk", 70000, 80000, sale=99000),
            lot(5, "The Martins Nest, The Banks, Blo Norton, Diss, Norfolk IP22 2JJ", 200000, 250000),
            lot(6, "Land adjacent to Cuffer Lane, New Buckenham, Norfolk NR16 2AY", 50000, 60000),
            lot(7, "Land at Berney Arms, Great Yarmouth, Norfolk NR30 1SB", 80000, 100000),
            lot(8, "Mardle Hall, Rectory Road, Tivetshall St Mary, Norwich, Norfolk NR15 2DD", 380000, 420000),
        ),
    },
    {
        "date": "2019-11-21",
        "url": "https://media.onthemarket.com/properties/7772028/1171489795/document-0.pdf",
        "lots": (
            lot(1, "Land at Low Road, Wortwell, Harleston, Norfolk IP20 0HJ", 25000, 30000),
            lot(2, "Land at Low Road, Wortwell, Harleston, Norfolk IP20 0HJ", 15000, 25000),
            lot(3, "Westgate Cottage, 21 Westgate, Hevingham, Norwich, Norfolk NR10 5NH", 250000, 275000),
            lot(4, "Land off Wells' Lane, Needham, Harleston, Norfolk", 40000, 50000),
            lot(5, "Old Cottage, East Church Street, Kenninghall, Norwich, Norfolk NR16 2EP", 150000, 170000),
            lot(6, "Land off Old Yarmouth Road, Broome, Norfolk NR35 2NZ", 35000, 45000),
            lot(7, "Land off Old Yarmouth Road, Broome, Norfolk NR35 2NZ", 20000, 30000),
            lot(8, "Land off Old Yarmouth Road, Broome, Norfolk NR35 2NZ", 20000, 40000),
            lot(9, "Land off Heywood Road, Winfarthing, Diss, Norfolk IP22 2DY", 30000, 40000),
        ),
    },
)

RESULT_ROWS = (
    lot(4, "Former Chapel, Welgate, Mattishall, Dereham, Norfolk", 110000, 130000, sale=156000),
    lot(5, "Pixey Green, Stradbroke, Eye, Suffolk", 20000, 30000, sale=43000),
    lot(8, "Land at Needham, Harleston, Norfolk", 50000, 60000, sale=174000),
    lot(9, "The Bungalow, Thornham Magna, Eye, Suffolk", None, None, sale=300000),
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,\xa0") or None


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value) or "", flags=re.I).strip().casefold()


def get(url):
    response = None
    for attempt in range(6):
        response = requests.get(url, headers=HEADERS, timeout=90)
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        time.sleep(min(2 ** attempt, 20))
    assert response is not None
    response.raise_for_status()
    if len(response.content) < 500:
        raise ValueError("source response is unexpectedly short")
    return response.url, response.content


def pdf_text(raw):
    reader = PdfReader(BytesIO(raw))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def validate_catalogue(text, spec):
    compact = normalized(text)
    parsed = datetime.strptime(spec["date"], "%Y-%m-%d")
    date_pattern = rf"\b{parsed.day}(?:st|nd|rd|th)?\s+{parsed.strftime('%B').casefold()}\s+{parsed.year}\b"
    if not re.search(date_pattern, clean(text).casefold()):
        raise ValueError(f"catalogue does not prove exact event date {spec['date']}")
    for row in spec["lots"]:
        # PDF text extraction can interleave the two brochure columns, so a
        # long contiguous address phrase is not stable.  Require the exact
        # postcode where published plus the distinctive premise/title tokens;
        # these survive column order without weakening row-level admission.
        title_tokens = normalized(row["address"].split(",", 1)[0]).split()
        title_tokens = title_tokens[: min(3, len(title_tokens))]
        postcode = corpus.PC.search(row["address"])
        required = list(title_tokens)
        if postcode:
            required.append(normalized(postcode.group()))
        missing = [token for token in required if token not in compact]
        if missing:
            raise ValueError(
                f"catalogue address evidence missing for lot {row['lot_number']}: {missing}"
            )
        guide_tokens = {str(row["guide_price"] // 1000), str(row["guide_price_high"] // 1000)}
        if not all(token in compact for token in guide_tokens):
            raise ValueError(f"catalogue guide evidence missing for lot {row['lot_number']}")
    return True


def validate_result_page(html):
    text = normalized(BeautifulSoup(html, "lxml").get_text(" ", strip=True))
    if not re.search(r"\b21(?:st|nd|rd|th)? march 2018\b", text):
        raise ValueError("result page does not prove 21 March 2018")
    for row in RESULT_ROWS:
        anchor = " ".join(normalized(row["address"]).split()[:3])
        if anchor not in text or str(row["sale_price"] // 1000) not in text:
            raise ValueError(f"result page evidence missing for lot {row['lot_number']}")
    return True


def evidence_snapshot(raw, name, source_url, basis):
    sha = hashlib.sha256(raw).hexdigest()
    path = corpus.DATA / "sources" / SLUG / f"{name}-{sha[:16]}.gz"
    if not path.exists():
        corpus.atomic(path, gzip.compress(raw, mtime=0))
    return {
        "source_url": source_url,
        "retrieved_at": corpus.now(),
        "sha256": sha,
        "snapshot_path": str(path.relative_to(corpus.ROOT)),
        "basis": basis,
    }


def appearance(event_date, row, original_url, evidence, source_basis):
    auction_id = f"{SLUG}:{event_date}"
    value = corpus.base_row(SOURCE, auction_id, event_date, row["lot_number"], None, original_url)
    address = row["address"]
    postcode = corpus.PC.search(address)
    guide_text = None
    if row["guide_price"] is not None:
        guide_text = f"Guide £{row['guide_price']:,}"
        if row["guide_price_high"] is not None:
            guide_text += f"–£{row['guide_price_high']:,}"
    sale_text = f"Sold £{row['sale_price']:,}" if row["sale_price"] is not None else None
    value.update(
        appearance_id=f"{SOURCE}|{auction_id}|lot:{row['lot_number']}",
        address=address,
        postcode=postcode.group().upper() if postcode else None,
        locality=address,
        description=row.get("description"),
        sector=corpus.sector(" ".join(filter(None, [address, row.get("description")]))),
        guide_price=row["guide_price"],
        guide_price_high=row["guide_price_high"],
        sale_price=row["sale_price"],
        status="sold" if row["sale_price"] is not None else "unknown",
        identity_method="first_party_exact_event_date_lot_number_and_reviewed_verbatim_address",
        record_quality="address_record",
        address_basis="verbatim individual lot address in retained first-party source",
        source_guide_text=guide_text,
        source_outcome_text=sale_text,
        auction_date_precision="day",
        auction_date_basis=source_basis,
        source_platform="TW Gaze first-party land and property archive",
        operator_legal_name=OPERATOR,
        operator_company_number=COMPANY_NUMBER,
        trading_name=SOURCE,
        source_evidence=evidence,
    )
    return value


def global_exact_appearances():
    values = defaultdict(list)
    for path in (corpus.DATA / "appearances").glob("*/*.jsonl.gz"):
        if path.parent.name == SLUG:
            continue
        for row in corpus.iter_rows(path):
            if row.get("auction_date") and row.get("address"):
                values[(row["auction_date"], normalized(row["address"]))].append(
                    {"appearance_id": row.get("appearance_id"), "auctioneer": row.get("auctioneer")}
                )
    return values


def persist_continuation(summary):
    path = corpus.DATA / "continuation_collection.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    checkpoint = {
        "source": SLUG,
        "outcome": "completed",
        "checked_at": summary["checked_at"],
        "run_new_appearances": summary["run_new_appearances"],
        "run_new_dated_twenty_year_address_records": summary["run_new_dated_twenty_year_address_records"],
        "run_new_commercial_or_mixed": summary["run_new_commercial_or_mixed"],
        "run_new_guide_prices": summary["run_new_guide_prices"],
        "run_new_sale_prices": summary["run_new_sale_prices"],
        "newly_covered_source_years": summary["newly_covered_source_years"],
        "duplicate_source_evidence_excluded": summary["run_duplicate_source_evidence_excluded"],
        "national_completeness_verified": False,
    }
    payload.setdefault("runs", []).append(checkpoint)
    payload.setdefault("latest_by_source", {})[SLUG] = checkpoint
    payload["last_automated_growth"] = checkpoint
    payload["next_growth_target"] = NEXT_TARGET
    payload["prepared_follow_on_target"] = {
        "checked_at": summary["checked_at"],
        "source_key_candidate": "tw-gaze-2023-03-15-catalogue",
        "auctioneer": SOURCE,
        "source_urls": [NEXT_URL],
        "source_format": "retained first-party land and property auction brochure PDF",
        "opportunity": "accessible exact-dated catalogue with uncaptured individual lots",
        "next_growth_target": NEXT_TARGET,
        "national_completeness_verified": False,
    }
    payload["national_completeness_verified"] = False
    corpus.save_json(path, payload)


def harvest():
    run_rows, states, catalogue_evidence = [], {}, {}
    for spec in CATALOGUES:
        resolved, raw = get(spec["url"])
        text = pdf_text(raw)
        validate_catalogue(text, spec)
        evidence = evidence_snapshot(raw, f"catalogue-{spec['date']}.pdf", resolved, "retained first-party exact-dated catalogue PDF")
        catalogue_evidence[spec["date"]] = evidence
        rows = [appearance(spec["date"], row, resolved, evidence, "exact date printed in first-party catalogue") for row in spec["lots"]]
        run_rows.extend(rows)
        state = {
            "auctioneer": SOURCE,
            "operator_legal_name": OPERATOR,
            "operator_company_number": COMPANY_NUMBER,
            "source_auction_id": f"{SLUG}:{spec['date']}",
            "auction_date": spec["date"],
            "source_url": resolved,
            "published_lot_denominator": len(spec["lots"]),
            "lots_captured": len(rows),
            "catalogue_complete": True,
            "denominator_reconciled": True,
            "completion_scope": "all individually numbered lots in the retained catalogue PDF",
            "source_evidence": evidence,
            "errors": [],
            "checked_at": corpus.now(),
        }
        corpus.save_json(corpus.DATA / "auctions" / SLUG / f"{spec['date']}.json", state)
        states[spec["date"]] = state

    try:
        resolved, raw = get(RESULT_URL)
    except requests.RequestException:
        resolved, raw = get(RESULT_FALLBACK_URL)
    html = raw.decode("utf-8", "replace")
    validate_result_page(html)
    evidence = evidence_snapshot(raw, "result-event-2018-03-21.html", resolved, "first-party exact-dated event result page")
    result_rows = [appearance("2018-03-21", row, resolved, evidence, "exact date published on first-party result event") for row in RESULT_ROWS]
    for row in result_rows:
        row["guide_source_evidence"] = catalogue_evidence["2019-11-21"]
        row["result_source_evidence"] = evidence
        row["guide_evidence_basis"] = "retrospective TW Gaze results panel reconciled by distinctive property, guide and achieved price"
    run_rows.extend(result_rows)
    result_state = {
        "auctioneer": SOURCE,
        "operator_legal_name": OPERATOR,
        "operator_company_number": COMPANY_NUMBER,
        "source_auction_id": f"{SLUG}:2018-03-21",
        "auction_date": "2018-03-21",
        "source_url": resolved,
        "published_result_denominator": len(RESULT_ROWS),
        "lots_captured": len(result_rows),
        "catalogue_complete": False,
        "source_rows_complete": True,
        "denominator_reconciled": True,
        "completion_scope": "all sold individual property rows exposed on retained first-party result page",
        "source_evidence": evidence,
        "errors": [],
        "checked_at": corpus.now(),
    }
    corpus.save_json(corpus.DATA / "auctions" / SLUG / "2018-03-21.json", result_state)
    states["2018-03-21"] = result_state

    exact = global_exact_appearances()
    overlaps, admissible = [], []
    for row in run_rows:
        matches = exact.get((row["auction_date"], normalized(row["address"])), [])
        if matches:
            overlaps.append({"appearance_id": row["appearance_id"], "address": row["address"], "auction_date": row["auction_date"], "existing": matches})
        else:
            admissible.append(row)

    path = corpus.DATA / "appearances" / SLUG / "canonical.jsonl.gz"
    existing = list(corpus.iter_rows(path)) if path.exists() else []
    before = {row["appearance_id"] for row in existing}
    merged = {row["appearance_id"]: row for row in existing}
    for row in admissible:
        merged[row["appearance_id"]] = row
    total = corpus.write_rows(f"{SLUG}/canonical", list(merged.values()))
    added = [row for key, row in merged.items() if key not in before]
    today = date.today().isoformat()
    cutoff = date(date.today().year - 20, date.today().month, date.today().day).isoformat()
    dated = [row for row in added if row.get("address") and cutoff <= row["auction_date"] <= today]
    years_before = {row["auction_date"][:4] for row in existing if row.get("auction_date")}
    years_after = {row["auction_date"][:4] for row in merged.values() if row.get("auction_date")}
    summary = {
        "checked_at": corpus.now(),
        "operator": {"canonical_name": SOURCE, "company_name": OPERATOR, "company_number": COMPANY_NUMBER, "branches_and_trading_names_are_not_counted_as_separate_auctioneers": True},
        "catalogues_captured": len(CATALOGUES),
        "result_events_captured": 1,
        "appearances_captured": total,
        "run_new_appearances": total - len(before),
        "run_new_address_records": sum(bool(row.get("address")) for row in added),
        "run_new_exact_dated_address_records": sum(bool(row.get("address") and row.get("auction_date")) for row in added),
        "run_new_dated_twenty_year_address_records": len(dated),
        "run_new_partial_lots": sum(not row.get("address") for row in added),
        "run_new_undated_lots": sum(not row.get("auction_date") for row in added),
        "run_new_future_dated_lots": sum(row.get("auction_date", today) > today for row in added),
        "run_new_guide_prices": sum(row.get("guide_price") is not None for row in added),
        "run_new_sale_prices": sum(row.get("sale_price") is not None for row in added),
        "run_new_rents": sum(row.get("annual_rent") is not None for row in added),
        "run_new_commercial_or_mixed": sum(row.get("sector") in {"commercial", "mixed", "mixed-use"} for row in added),
        "source_years": sorted(years_after),
        "newly_covered_source_years": sorted(years_after - years_before),
        "by_sector": dict(Counter(row.get("sector") for row in merged.values())),
        "by_status": dict(Counter(row.get("status") for row in merged.values())),
        "auctions": states,
        "run_duplicate_source_evidence_excluded": len(overlaps),
        "duplicate_source_evidence_exclusions": overlaps,
        "retrospective_result_rows_not_banked_without_exact_event": ["Hopton, guide £140,000–£170,000, sold £202,000", "Kenninghall, guide £80,000–£120,000, sold £160,000"],
        "national_completeness_verified": False,
    }
    corpus.save_json(corpus.DATA / "tw_gaze_collection.json", summary)
    persist_continuation(summary)
    print(json.dumps(summary, indent=2), flush=True)
    if len(states) != len(CATALOGUES) + 1:
        raise SystemExit(1)
    return summary


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    harvest()
