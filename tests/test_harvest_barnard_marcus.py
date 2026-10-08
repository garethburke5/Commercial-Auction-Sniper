import scripts.harvest_barnard_marcus as collector


def test_reconciled_search_inventory_declares_standard_catalogue_completeness(monkeypatch):
    monkeypatch.setattr(collector, "parse_ids", lambda _url: ("house", "auction"))
    monkeypatch.setattr(collector, "fetch_json", lambda _url: {
        "pagination": {"pageCount": 1, "currentPage": 1, "totalCount": 1},
        "items": [{
            "id": 42,
            "lotNumber": "1",
            "addressLine1": "1 High Street",
            "addressLine2": "London, SW1A 1AA",
            "description": "A residential and commercial mixed-use property",
            "priceDescriptor": "Sold for",
            "price": "£250,000",
            "showPriceAsterix": False,
            "statusLabel": "Sold",
            "url": "https://www.barnardmarcusauctions.co.uk/auctions/example/42/",
            "image": "/media/example.jpg",
        }],
    })

    payload = collector.harvest(
        "https://www.barnardmarcusauctions.co.uk/auctions/example/",
        "2026-02-03",
    )

    assert payload["catalogue_complete"] is True
    assert payload["catalogue_lot_count"] == 1
    assert payload["published_rows"] == payload["source_reported_rows"] == 1
    assert payload["reconciliation_shortfall"] == 0
    assert payload["lot_records"][0]["source_record_id"] == "barnard-marcus-property:42"
    assert payload["lot_records"][0]["result_price_gbp"] == 250_000
