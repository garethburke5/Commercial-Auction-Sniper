from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_auction_hammer_midlands as hammer


def test_auction_title_and_legacy_day_month_reconcile():
    candidate = hammer.auction_date_from_title("Livestream 08-12-2022 11:00")
    assert candidate == "2022-12-08"
    assert hammer.resolve_property_date("Auction On Thursday 8 December at 11am", candidate) == (
        "2022-12-08", "published day/month reconciled to contemporaneous first-party auction post"
    )
    assert hammer.resolve_property_date("Auction On Thursday 9 December at 11am", candidate) == (None, None)


def test_explicit_property_date_overrides_preceding_event():
    assert hammer.resolve_property_date("Auction: 4th November 2026", "2026-09-16") == (
        "2026-11-04", "explicit property auction field"
    )


def test_rent_requires_current_income_and_excludes_ground_rent():
    assert hammer.parse_rent("Current rent of £525 per calendar month") == (
        6300, "Current rent of £525 per calendar month"
    )
    assert hammer.parse_rent("Rental income of £12,500 per annum") == (
        12500, "Rental income of £12,500 per annum"
    )
    assert hammer.parse_rent("tenant in situ paying £425 per calendar month") == (
        5100, "tenant in situ paying £425 per calendar month"
    )
    assert hammer.parse_rent("currently let to a takeaway user for a weekly rent of £228") == (
        11856, "currently let to a takeaway user for a weekly rent of £228"
    )
    assert hammer.parse_rent("Ground rent £250 per annum and service charge £900") == (None, None)


def test_property_parser_preserves_stable_identity_guide_and_future_date():
    page = """
    <html><head><meta name="description" content="Two bedroom house"></head><body><main>
    <div>LOT 21</div><h1>33 Lincoln Road, Burslem, Stoke-On-Trent, ST6 3DE</h1>
    <div>Guide Price: £70,000+ plus fees</div><a href="https://legal.test/pack">DOWNLOAD LEGAL PACK</a>
    <div>Auction: 4th November 2026</div><div>Tenure: Freehold</div>
    <p>Residential for Improvement</p></main></body></html>
    """
    item = {"id": 5465, "link": "https://example.test/property/33-lincoln-road/"}
    row = hammer.parse_property(page, item, "2026-09-16", {"sha256": "abc"})
    assert row["appearance_id"] == "Auction Hammer Midlands|wp-property:5465|2026-11-04"
    assert row["auction_date"] == "2026-11-04"
    assert row["address"].startswith("33 Lincoln Road") and row["postcode"] == "ST6 3DE"
    assert row["guide_price"] == 70000 and row["sale_price"] is None
    assert row["record_quality"] == "address_record"


def test_missing_property_date_uses_adjacent_first_party_event_only_as_fallback():
    page = """<main><div>LOT 21</div><h1>4 Maurice Lee Avenue, Telford, TF2 6HE</h1>
    <div>Sold After</div><div>Guide Price: £85,000 plus fees</div><p>Residential.</p></main>"""
    item = {"id": 1534, "link": "https://example.test/property/maurice/"}
    row = hammer.parse_property(page, item, ["2023-01-31", "2023-03-16"], {}, "2023-01-31")
    assert row["auction_date"] == "2023-01-31"
    assert row["auction_date_basis"].startswith("nearest preceding")


def test_postcode_free_page_is_partial_not_an_address_record():
    page = """<main><div>LOT TBC</div><h1>23 Britannia Street, Leek</h1>
    <div>Sold Prior</div><div>Guide Price: £145,000 plus fees</div>
    <p>Live stream auction on 6TH JUNE 2023 1PM START.</p></main>"""
    item = {"id": 1612, "link": "https://example.test/property/leek/"}
    row = hammer.parse_property(page, item, "2023-06-06", {})
    assert row["address"] is None and row["postcode"] is None
    assert row["locality"] == "23 Britannia Street, Leek"
    assert row["record_quality"] == "partial_lot" and row["status"] == "sold_prior"
