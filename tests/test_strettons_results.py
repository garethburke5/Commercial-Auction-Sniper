from scripts.harvest_strettons_results import (
    discover_auctions,
    include_recovered_auctions,
    parse_detail,
    status_and_price,
)


INDEX = [{
    "crm_id": "3605", "auctionDate": "2026-04-16T11:00:00.000Z",
    "auctionType": "past", "publish": True, "updatedAt": "2026-04-17T10:00:00.000Z",
}]

DETAIL = {
    "result": {"pageContext": {"auctionId": "3605", "properties": [
        {
            "id": "prop-a", "slug": "commercial-shop-for-sale-in-one-high-street-e1-1aa",
            "department": "auction_commercial", "display_address": "1 High Street, London E1 1AA",
            "status": "Sold", "price": 200000, "title": "commercial shop for sale",
            "alt_lot_number": 2, "auctionDate": "2026-04-16T11:00:00.000Z",
            "building": ["retail"],
            "extra": {"lotNumber": "2", "tagline": "FREEHOLD SHOP", "resultPrice": "Sold for £251,000"},
        },
        {
            "id": "prop-b", "slug": "residential-flat-for-sale-in-no-postcode",
            "department": "auction_residential", "display_address": "Flat above the parade",
            "status": None, "price": 85000, "title": "residential flat for sale",
            "alt_lot_number": 7, "auctionDate": "2026-04-16T11:00:00.000Z",
            "building": ["flat"],
            "extra": {"lotNumber": "7", "tagline": "VACANT LEASEHOLD FLAT"},
        },
    ]}}
}


def test_index_discovers_published_auction_identity_and_timestamp():
    assert discover_auctions(INDEX) == [{
        "auction_id": "3605", "auction_date": "2026-04-16",
        "updated_at": "2026-04-17T10:00:00.000Z", "summary": INDEX[0],
    }]


def test_embedded_rows_preserve_commercial_residential_and_partial_lots():
    expected = discover_auctions(INDEX)[0]
    state, rows = parse_detail(DETAIL, expected, {"sha256": "x"})
    assert state["catalogue_complete"] is True
    assert state["pagination_reconciled"] is True
    assert state["lots_captured"] == 2
    assert rows[0]["sector"] == "commercial"
    assert rows[0]["sale_price"] == 251000
    assert rows[0]["guide_price"] == 200000
    assert rows[0]["postcode"] == "E1 1AA"
    assert rows[1]["sector"] == "residential"
    assert rows[1]["address"] is None
    assert rows[1]["locality"] == "Flat above the parade"
    assert rows[1]["record_quality"] == "partial_lot"
    assert len({row["appearance_id"] for row in rows}) == 2


def test_result_statuses_are_separate_from_guides():
    assert status_and_price("Sold", "Sold for £251,000") == ("sold", 251000)
    assert status_and_price("Sold", "Sold prior to auction, for an undisclosed amount") == ("sold_prior", None)
    assert status_and_price("Withdrawn", "Withdrawn") == ("withdrawn", None)


def test_blocked_recovery_evidence_is_not_reprobed_as_a_catalogue():
    indexed = discover_auctions(INDEX)
    recovered = include_recovered_auctions(indexed)
    assert [item["auction_id"] for item in recovered] == ["3605"]
    assert recovered[0]["updated_at"] == "2026-04-17T10:00:00.000Z"
