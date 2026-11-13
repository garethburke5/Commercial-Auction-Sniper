from scripts import harvest_fisher_german_legacy as source


def test_retained_manifest_has_eight_distinct_exact_dated_interests():
    assert len(source.EVENT_LOTS) == 8
    assert len({row["source_lot_id"] for row in source.EVENT_LOTS}) == 8
    assert sum(row["sector"] == "land" for row in source.EVENT_LOTS) == 6
    assert sum(row.get("guide_price") is not None for row in source.EVENT_LOTS) == 3


def test_event_rows_preserve_guide_ranges_and_traditional_format():
    evidence = {"source_url": "https://example.test/lot.pdf", "sha256": "a" * 64}
    newsletter = {"source_url": "https://example.test/newsletter", "sha256": "b" * 64}
    lot = next(row for row in source.EVENT_LOTS if row["source_lot_id"].endswith("1-churton-road"))
    row = source.event_appearance(lot, newsletter, evidence)
    assert row["auction_date"] == "2017-02-15"
    assert row["guide_price"] == 100000
    assert row["guide_price_high"] == 130000
    assert row["sale_price"] is None
    assert row["auction_format"] == "traditional room auction"
    assert row["auctioneer"] == "Fisher German Online Auction"


def test_retrospective_results_remain_year_precision_and_keep_prices_distinct():
    evidence = {"source_url": "https://example.test/newsletter", "sha256": "b" * 64}
    row = source.retrospective_appearance(source.RETROSPECTIVE_RESULTS[0], evidence)
    assert row["auction_date"] is None
    assert row["auction_year"] == 2016
    assert row["auction_date_precision"] == "year"
    assert row["guide_price"] == 200000
    assert row["guide_price_high"] == 250000
    assert row["sale_price"] == 310000
    assert row["status"] == "sold"


def test_newsletter_validation_requires_links_results_and_event_inventory():
    links = "".join(f'<a href="{path}">{key}</a>' for key, path in source.DOCUMENTS.items())
    html = f"""
      <h1>Fisher German Regional Newsletter issue 6</h1>
      <p>Our first auction of 2017 is on 15 th February.</p>
      <p>Available in 5 lots. 1 Churton Road Farndon Chester.</p>
      <p>2 Churton Road Farndon Chester. Single block of amenity land at Great Barrow.</p>
      <p>No. 3 Broad Lane, Aughton, Ormskirk. Sold for £310.000.</p>
      <p>The first at Bradwall, near Sandbach sold for £172,000.</p>
      {links}
    """
    source.validate_newsletter(html)
