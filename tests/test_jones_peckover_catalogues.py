from scripts import harvest_jones_peckover_catalogues as jp


EVENT = {
    "auction_date": "2026-06-10",
    "source_url": "https://example.test/catalogue.pdf",
    "source_format": "pdf",
    "expected_text": ["Pen y Bryn Farm", "Guide Price £80,000"],
    "lots": [
        {
            "lot_number": "2",
            "source_lot_id": "2026-06-10-pen-y-bryn-2",
            "address": "Lot 2, Land at Pen y Bryn Farm, Penycae, LL14 1UA",
            "postcode": "LL14 1UA",
            "description": "7.89 acres and a stone outbuilding.",
            "sector": "land",
            "guide_price": 80000,
            "guide_price_text": "Guide Price £80,000",
            "status": "unknown",
        }
    ],
}


def test_manifest_event_requires_source_postcode_and_guide():
    jp.validate_event(
        EVENT,
        "Pen y Bryn Farm LL14 1UA Guide Price £80,000 Wednesday 10 June 2026",
    )


def test_manifest_event_preserves_individual_interest_identity_and_null_outcome():
    row = jp.event_rows(EVENT, {"sha256": "abc"})[0]
    assert row["appearance_id"] == "Jones Peckover|catalogue-lot:2026-06-10-pen-y-bryn-2"
    assert row["auction_date"] == "2026-06-10"
    assert row["lot_number"] == "2"
    assert row["guide_price"] == 80000
    assert row["sale_price"] is None
    assert row["status"] == "unknown"
    assert row["sector"] == "land"
