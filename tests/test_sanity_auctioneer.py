from datetime import date

from scripts.harvest_sanity_auctioneer import (
    guide_range,
    published_auction_date,
    row_from_property,
)


def evidence():
    return {
        "source_url": "https://www.auctionagent.co.uk/sold-properties",
        "snapshot_path": "data/auction_history/sources/auction-agent/sanity/example.json.gz",
        "retrieved_at": "2026-11-08T00:00:00+00:00",
        "sha256": "a" * 64,
        "basis": "test",
    }


def test_published_auction_date_requires_auction_context():
    assert published_auction_date(
        "Bidding will take place on Tuesday 10th November 2026 at 12pm."
    ) == "2026-11-10"
    assert published_auction_date("Lease dated Tuesday 10th November 2026") is None
    assert published_auction_date("Auction on Tuesday 31st November 2026") is None


def test_guide_range_preserves_low_and_high():
    assert guide_range("£25,000/£50,000") == (25000, 50000)
    assert guide_range("Guide price £65,000") == (65000, None)
    assert guide_range(None) == (None, None)


def test_sold_property_preserves_status_but_not_unpublished_achieved_price():
    item = {
        "_id": "stable-sold-id",
        "slug": {"current": "15-prairie-crescent-burnley-bb10-1eu"},
        "title": "15 Prairie Crescent",
        "location": "Burnley, BB10 1EU",
        "fullAddress": "15 Prairie Crescent, Burnley, BB10 1EU",
        "guidePrice": "£100,000/£150,000",
        "propertyStatus": "SOLD STC",
        "soldAt": "2026-09-30T11:01:00.000Z",
        "description": "A semi detached residential house.",
        "type": "Semi Detached House",
        "tenure": "See legal pack",
        "epc": "D",
        "features": "Three bedrooms",
        "imageUrls": ["https://cdn.sanity.io/example.jpg"],
    }
    row = row_from_property(
        item, "Auction Agent", "auction-agent", "www.auctionagent.co.uk", evidence()
    )
    assert row["appearance_id"] == "Auction Agent|sanity:stable-sold-id"
    assert row["auction_date"] == "2026-09-30"
    assert row["auction_date_basis"].startswith("exact soldAt")
    assert row["guide_price"] == 100000
    assert row["guide_price_high"] == 150000
    assert row["sale_price"] is None
    assert row["status"] == "sold stc"
    assert row["postcode"] == "BB10 1EU"
    assert row["record_quality"] == "address_record"


def test_current_property_uses_explicit_future_auction_date():
    item = {
        "_id": "stable-current-id",
        "slug": {"current": "derwent-buck-street-bradford-bd3-9qp"},
        "title": "Derwent, Buck Street",
        "location": "Bradford, BD3 9QP",
        "guidePrice": "£25,000/£50,000",
        "propertyStatus": "FOR AUCTION",
        "soldAt": None,
        "description": (
            "For sale by online auction starting on Tuesday 10th November 2026, "
            "bidding will be on the Auction Agent website. Commercial property."
        ),
        "type": "Other",
        "tenure": "Freehold",
        "features": "Shop unit",
        "imageUrls": [],
    }
    row = row_from_property(
        item, "Auction Agent", "auction-agent", "www.auctionagent.co.uk", evidence()
    )
    assert row["auction_date"] == "2026-11-10"
    assert row["auction_date_basis"].startswith("explicit auction date")
    assert row["status"] == "for auction"
    assert row["sector"] == "commercial"
    assert row["sale_price"] is None
    assert date.fromisoformat(row["auction_date"]) > date(2026, 11, 8)


def test_sold_label_without_date_remains_undated():
    item = {
        "_id": "stable-undated-id",
        "slug": {"current": "land-oakwood-court"},
        "title": "Land Oakwood Court",
        "location": "Bradford, BD8 8EY",
        "guidePrice": "£25,000/£50,000",
        "propertyStatus": "SOLD PRIOR",
        "soldAt": None,
        "description": "A parcel of land sold prior.",
        "type": "Other",
        "tenure": "See legal pack",
        "features": "Land",
        "imageUrls": [],
    }
    row = row_from_property(
        item, "Auction Agent", "auction-agent", "www.auctionagent.co.uk", evidence()
    )
    assert row["auction_date"] is None
    assert row["status"] == "sold prior"
    assert row["sale_price"] is None
    assert row["auction_date_basis"].startswith("no individual date")
