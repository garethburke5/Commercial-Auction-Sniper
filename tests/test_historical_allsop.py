import historical_allsop as a


def test_convert_preserves_residential_and_commercial_fields():
    raw = {"allsop_lotid": "lot-1", "allsop_auctionid": "auction-1", "allsop_lotnumber": 7,
           "auction_date": 1747868400000, "full_address": "10 High Street, London, SW1A 1AA",
           "allsop_name": "C250521 007", "property_byline": "Shop and Flat Investment",
           "property_types": ["Retail", "Flat / Block"], "is_commercial": True, "is_residential": True,
           "property_tenure": "Freehold", "guide_price_lower": 200000, "guide_price_upper": 220000,
           "lot_status": "Sold", "sale_price": "250000.00", "current_rent_per_annum": 18000,
           "featured_image_file_id": "image-1"}
    row, reason = a.convert(raw, {"snapshot_path": "page-1.json.gz"})
    assert reason is None
    assert row["auction_date"] == "2025-05-21"
    assert row["address"] == "10 High Street, London, SW1A 1AA"
    assert row["sector"] == "mixed-use"
    assert row["guide_price"] == 200000 and row["sale_price"] == 250000
    assert row["annual_rent"] == 18000 and row["record_quality"] == "address_record"


def test_explicit_test_and_lot_zero_rows_are_excluded():
    base = {"allsop_lotid": "lot-1", "allsop_auctionid": "auction-1",
            "auction_date": 921888000000, "allsop_name": "R990301 001"}
    row, reason = a.convert({**base, "allsop_lotnumber": 1,
                             "full_address": "TEST 3 - 12 Shamrock Way, London, N14 5RY"}, {})
    assert row is None and reason == "explicit test record"
    row, reason = a.convert({**base, "allsop_lotnumber": 0, "full_address": "Commercial Section"}, {})
    assert row is None and "lot-zero" in reason


def test_epoch_day_accepts_manifest_iso_and_search_epoch():
    assert a.epoch_day("2026-09-16T23:00:00.000000Z") == "2026-09-17"
    assert a.epoch_day(1747868400000) == "2025-05-22"


def test_reference_day_is_preferred_over_inconsistent_timestamp():
    assert a.reference_day("R130917 137") == "2013-09-17"
    assert a.auction_day({"allsop_auctionreference": "C250521",
                          "allsop_auctiondate": "2025-05-22T00:00:00Z"}) == "2025-05-21"
