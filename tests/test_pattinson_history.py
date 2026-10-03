import pytest

from scripts.harvest_pattinson_history import (
    card_row,
    compose_address,
    discover_property_ids,
    historical_auction,
    published_past_deadline,
)


def test_sitemap_denominator_is_unique_and_first_party():
    xml = """<urlset>
      <url><loc>https://www.pattinson.co.uk/property/468878</loc></url>
      <url><loc>https://www.pattinson.co.uk/property/493535</loc></url>
    </urlset>"""
    assert discover_property_ids(xml) == ["468878", "493535"]
    with pytest.raises(ValueError, match="duplicate"):
        discover_property_ids(xml + "https://www.pattinson.co.uk/property/468878")


def test_only_explicit_sold_online_auction_cards_are_historical():
    base = {"id": 468878, "isSold": True, "isOnlineAuction": True, "isRental": False}
    assert historical_auction(base)
    assert not historical_auction({**base, "isSold": False})
    assert not historical_auction({**base, "isOnlineAuction": False})
    assert not historical_auction({**base, "isRental": True})


def test_structured_address_discards_placeholder_and_preserves_postcode():
    address, postcode, locality = compose_address({
        "houseNameNumber": "Flat 2 - Swallow Hill Works", "street": "353 Tong Road",
        "locality": ".", "city": "Leeds", "county": "West Yorkshire", "postcode": "ls12 4qg",
    })
    assert address == "Flat 2 - Swallow Hill Works, 353 Tong Road, Leeds, West Yorkshire, LS12 4QG"
    assert postcode == "LS12 4QG" and locality == "Leeds"


def test_unknown_or_future_deadline_is_not_invented_as_history_date():
    observed = "2026-10-03T12:00:00+00:00"
    assert published_past_deadline(None, observed) is None
    assert published_past_deadline("2025-04-22T12:00:00Z", observed) == "2025-04-22"
    assert published_past_deadline("2026-10-04T12:00:00Z", observed) is None


def test_card_row_preserves_first_party_id_and_starting_bid_semantics():
    card = {
        "id": 493535, "isSold": True, "isOnlineAuction": True, "isRental": False,
        "price": 190000, "priceDescription": "Starting Bid", "tenure": "Freehold",
        "propertyTypeName": "Terraced House", "headline": "Secure Sale online bidding",
        "salesDescription": "4 bed terraced house to buy in PO1", "bedrooms": 4,
        "bathrooms": 1, "receptions": 1,
        "address": {"houseNameNumber": "16", "street": "Newcome Road", "city": "Portsmouth", "county": "Hampshire", "postcode": "PO1 5DU"},
        "propertyImages": [{"image": "https://example.invalid/one.jpg"}],
    }
    row = card_row(card, {"sha256": "x"}, "2026-10-03T12:00:00+00:00")
    assert row["appearance_id"] == "Pattinson Auctions|property:493535"
    assert row["source_auction_id"] == "pattinson-online-property:493535"
    assert row["auction_date"] is None
    assert row["status"] == "sold" and row["sale_price"] is None
    assert row["guide_price"] == 190000
    assert row["address"] == "16, Newcome Road, Portsmouth, Hampshire, PO1 5DU"
    assert row["record_quality"] == "address_record"
