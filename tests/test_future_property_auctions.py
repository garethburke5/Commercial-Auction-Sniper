import pytest

from scripts.harvest_future_property_auctions import (
    epoch_date,
    manifest_rows,
    parse_auction,
    sanitized_snapshot,
)


UUID = "auction-uuid"
LISTING = "listing-uuid"
PAYLOAD = {
    "information": {
        "auction": {"uuid": UUID, "endsAt": 1790863200000},
        "listings": {LISTING: {
            "uuid": LISTING, "id": 42, "auctionUuid": UUID, "lotNumber": "7",
            "title": "10&nbsp;High Street, Glasgow G1 1AA",
            "description": '<p>Retail investment</p><a href="property_details.asp?id=14500001">details</a>',
            "summary": "Tenanted&nbsp;Freehold&nbsp;Commercial",
            "images": ["image-uuid"],
        }},
    },
    "sellingInformation": {
        "sales": {LISTING: {"totalBids": 4, "reserve": 100000}},
        "saleStatuses": {LISTING: {
            "listingUuid": LISTING, "complete": True, "sold": True,
            "withdrawn": False, "suspended": False, "endsAt": 1790863200000,
            "highestBidUuid": "bid-uuid",
        }},
        "bids": {"bid-uuid": {
            "uuid": "bid-uuid", "listingUuid": LISTING, "amount": 125000,
            "placedAt": 1790863100000, "userUuid": "must-not-survive", "cancelled": False,
        }},
    },
    "attachments": {"image-uuid": {
        "uuid": "image-uuid", "basePath": "https://media.test/image/upload/",
        "versionAndPublicId": "v1/folder/image.jpg",
    }},
    "registrants": {"must-not-survive": {"name": "private"}},
}
MANIFEST = {
    "auction_uuid": UUID, "auction_id": "123", "title": "1 October 2026",
    "auction_end_time": 1790863200000, "auction_date": "2026-10-01",
}


def test_manifest_requires_stable_distinct_auction_identities():
    rows = manifest_rows({"basicAuctionBidJSModelList": [{
        "auctionUuid": UUID, "auctionId": 123, "auctionTitle": "Auction",
        "auctionEndTime": 1790863200000,
    }]})
    assert rows[0]["auction_date"] == "2026-10-01"
    with pytest.raises(ValueError, match="duplicate"):
        manifest_rows({"basicAuctionBidJSModelList": [
            {"auctionUuid": UUID, "auctionId": 1}, {"auctionUuid": UUID, "auctionId": 2},
        ]})


def test_complete_payload_banks_address_outcome_price_and_provenance():
    rows, state = parse_auction(PAYLOAD, MANIFEST, {"sha256": "abc", "source_url": "api"})
    assert len(rows) == 1 and state["catalogue_complete"] is True
    row = rows[0]
    assert row["address"] == "10 High Street, Glasgow G1 1AA"
    assert row["postcode"] == "G1 1AA"
    assert row["sale_price"] == 125000 and row["status"] == "sold"
    assert row["property_id"] == "14500001"
    assert row["image_urls"] == ["https://media.test/image/upload/v1/folder/image.jpg"]
    assert row["appearance_id"].endswith("listing:listing-uuid")


def test_snapshot_strips_people_bid_histories_and_hidden_reserve():
    snapshot = sanitized_snapshot(PAYLOAD, {"sha256": "abc"})
    text = str(snapshot)
    assert "must-not-survive" not in text
    assert "reserve" not in snapshot["public_sales"][LISTING]
    assert 100000 not in snapshot["public_sales"][LISTING].values()
    assert snapshot["public_sales"][LISTING]["highestBid"]["amount"] == 125000


def test_non_reconciling_payload_is_rejected():
    broken = {**PAYLOAD, "sellingInformation": {**PAYLOAD["sellingInformation"], "sales": {}}}
    with pytest.raises(ValueError, match="do not reconcile"):
        parse_auction(broken, MANIFEST, {})


def test_epoch_date_is_utc_and_null_safe():
    assert epoch_date(1790863200000) == "2026-10-01"
    assert epoch_date(None) is None
