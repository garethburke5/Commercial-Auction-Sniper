from datetime import datetime, timezone
import json

from scripts.harvest_bamboo_auctioneer import extract_next_data, row_from_property


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
    )
    assert row["appearance_id"] == "247 Property Auctions|bamboo:63440bcd111e9348081dd163"
    assert row["auction_date"] == "2022-11-03"
    assert row["guide_price"] == 130000
    assert row["sale_price"] == 129000
    assert row["status"] == "sold"
    assert row["sector"] == "mixed-use"
    assert row["record_quality"] == "address_record"


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
