from datetime import datetime, timezone
import json

from scripts.harvest_bamboo_auctioneer import (
    bamboo_sector,
    extract_next_data,
    published_rent,
    row_from_property,
)


def test_extract_next_data():
    payload = {"props": {"pageProps": {"propertiesData": {"data": [], "meta": {"totalCount": 0}}}}}
    raw = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(payload)
        + "</script></html>"
    ).encode()
    assert extract_next_data(raw) == payload


def test_row_preserves_exact_close_prices_and_identity():
    item = {
        "_id": "63440bcd111e9348081dd163",
        "handle": "mixed-commercial-and-residential-investment-property-2369246",
        "title": "Mixed commercial and residential investment property",
        "type": "Retail with flats",
        "tenure": "Freehold",
        "description": "<p>Shop with two flats above.</p>",
        "fullAddress": "3 Fore Street, Torpoint, PL11 2AA",
        "city": "Torpoint",
        "postcode": "PL11 2AA",
        "endDate": "2022-11-03T14:00:00.000Z",
        "guidePrice": 130000,
        "highestBid": 129000,
        "isReserveMet": True,
        "status": "published",
        "bids": [{"amount": 129000}],
        "galleryImages": [],
    }
    row = row_from_property(
        item,
        "247 Property Auctions",
        "247-property-auctions",
        "247auction.bambooauctions.com",
        {"source_url": "https://247auction.bambooauctions.com/"},
        datetime(2026, 10, 26, tzinfo=timezone.utc),
        operator_legal_name="EXAMPLE AUCTIONS LIMITED",
        operator_company_number="01234567",
    )
    assert row["appearance_id"] == "247 Property Auctions|bamboo:63440bcd111e9348081dd163"
    assert row["auction_date"] == "2022-11-03"
    assert row["guide_price"] == 130000
    assert row["sale_price"] == 129000
    assert row["status"] == "sold"
    assert row["sector"] == "mixed-use"
    assert row["record_quality"] == "address_record"
    assert row["operator_legal_name"] == "EXAMPLE AUCTIONS LIMITED"
    assert row["operator_company_number"] == "01234567"


def test_unmet_reserve_does_not_become_sale_evidence():
    item = {
        "_id": "source-id",
        "handle": "a-property-1",
        "title": "Land",
        "type": "Land",
        "fullAddress": "Land at Example Road, EX1 1AA",
        "city": "Exeter",
        "postcode": "EX1 1AA",
        "endDate": "2021-01-02T12:00:00.000Z",
        "guidePrice": 50000,
        "highestBid": 48000,
        "isReserveMet": False,
        "status": "published",
        "bids": [{"amount": 48000}],
    }
    row = row_from_property(
        item,
        "Example",
        "example",
        "example.bambooauctions.com",
        {},
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert row["status"] == "unknown"
    assert row["sale_price"] is None


def test_missing_close_date_is_preserved_as_undated():
    item = {
        "_id": "undated-id",
        "handle": "an-undated-property-1",
        "title": "A property",
        "type": "House",
        "fullAddress": "1 Example Road, EX1 1AA",
        "postcode": "EX1 1AA",
        "guidePrice": 100000,
        "isReserveMet": False,
        "status": "published",
    }
    row = row_from_property(
        item,
        "Example",
        "example",
        "example.bambooauctions.com",
        {},
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert row["auction_date"] is None
    assert row["status"] == "unknown"
    assert row["auction_date_basis"].startswith("no close date")


def test_index_summary_can_bank_when_retired_detail_payload_is_missing():
    item = {
        "_id": "stable-1",
        "handle": "retired-lot",
        "endDate": "2025-01-02T12:00:00.000Z",
        "addressLineOne": "1 High Street",
        "city": "Exeter",
        "postcode": "EX1 1AA",
        "type": "Commercial",
        "guidePrice": 100000,
    }
    row = row_from_property(
        item, "Stags", "stags", "stags.bambooauctions.com", {},
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert row["address"] == "1 High Street, Exeter, EX1 1AA"
    assert row["auction_date"] == "2025-01-02"
    assert row["guide_price"] == 100000 and row["sale_price"] is None


def test_asset_type_wins_over_neighbourhood_commercial_words():
    description = "Pasture land near a village public house, shop, restaurant and hotel."
    assert bamboo_sector("Land", "Land at Example", "Land at Example", description) == "land"
    assert bamboo_sector("Detached", "House", "1 High Street", description) == "residential"


def test_published_rent_is_preserved_without_inference():
    assert published_rent("The shop produces £12,500 per annum.") == (12500, "£12,500 per annum")
    assert published_rent("Vacant possession; estimated rental value £12,500") == (None, None)
