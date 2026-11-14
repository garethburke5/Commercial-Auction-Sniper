from datetime import datetime, timezone
import json

from scripts.harvest_bamboo_auctioneer import (
    duplicate_evidence_reason,
    extract_next_data,
    marketplace_attribution,
    property_payload,
    published_auction_date,
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


def test_property_payload_accepts_marketplace_and_fusion_shapes():
    for key in ("propertyData", "propertyResponse"):
        payload = {"props": {"pageProps": {key: {"_id": "lot-id", "handle": "lot"}}}}
        raw = (
            '<html><script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(payload)
            + "</script></html>"
        ).encode()
        assert property_payload(raw)["_id"] == "lot-id"


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
        "EXAMPLE AUCTIONS LIMITED",
        "12345678",
        ["Example Auctions"],
    )
    assert row["appearance_id"] == "247 Property Auctions|bamboo:63440bcd111e9348081dd163"
    assert row["auction_date"] == "2022-11-03"
    assert row["guide_price"] == 130000
    assert row["sale_price"] == 129000
    assert row["status"] == "sold"
    assert row["sector"] == "mixed-use"
    assert row["record_quality"] == "address_record"
    assert row["operator_legal_name"] == "EXAMPLE AUCTIONS LIMITED"
    assert row["operator_company_number"] == "12345678"
    assert row["historical_trading_names_not_counted_as_auctioneers"] == ["Example Auctions"]


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


def test_fusion_bid_timestamp_recovers_event_date_without_inventing_end_time():
    item = {
        "_id": "fusion-id",
        "handle": "retired-lot",
        "title": "Land",
        "type": "Land",
        "fullAddress": "Land at Example Road, EX1 1AA",
        "postcode": "EX1 1AA",
        "guidePrice": 80000,
        "highestBid": 88000,
        "isReserveMet": True,
        "bids": [
            {"amount": 80000, "createdAt": "2023-04-27T17:44:33.286Z"},
            {"amount": 88000, "createdAt": "2023-04-27T17:45:03.097Z"},
        ],
    }
    row = row_from_property(
        item,
        "Example",
        "example",
        "example.test",
        {},
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert row["auction_date"] == "2023-04-27"
    assert row["auction_end_time"] is None
    assert row["auction_date_basis"].startswith("exact event date from latest published bid")
    assert row["sale_price"] == 88000


def test_description_recovers_only_explicit_auction_date():
    item = {
        "description": (
            "Planning permission dated 3rd May 2023. "
            "Live/hybrid auction, ending on 19th November 2026."
        )
    }
    assert published_auction_date(item) == (
        "2026-11-19",
        None,
        "exact auction date explicitly published in retained Bamboo property description",
    )


def test_published_rent_requires_context_and_annualises_cadence():
    assert published_rent("Currently tenanted with a rental income of £200 PCM") == (
        2400,
        "tenanted with a rental income of £200 PCM",
    )
    assert published_rent("Guide price £200 per month") == (None, None)


def test_marketplace_attribution_keeps_branch_as_provenance():
    auctioneer, provenance = marketplace_attribution({
        "organisation": "example",
        "organisationDetails": {
            "_id": "org-id",
            "name": "example",
            "display": "Example Auctions",
            "externalAddress": "https://example.test/auctions",
            "branch": {"_id": "branch-id", "name": "city", "display": "City Branch"},
        },
    })
    assert auctioneer == "Example Auctions"
    assert provenance["source_organisation_id"] == "org-id"
    assert provenance["source_branch_display"] == "City Branch"
    assert provenance["branch_not_counted_as_auctioneer"] is True


def test_duplicate_evidence_requires_more_than_date_and_address():
    row = {"guide_price": 100000, "sale_price": None, "description": "A shop and flat"}
    assert duplicate_evidence_reason(row, [{"guide_price": 100000}]) == "exact date/address and guide price"
    assert duplicate_evidence_reason(row, [{"guide_price": 90000, "description": "A separate garage"}]) is None
