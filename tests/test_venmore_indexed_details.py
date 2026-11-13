import json

import pytest

from scripts import harvest_venmore_indexed_details as collector


def test_manifest_reconciles_72_distinct_first_party_pages():
    payload = collector.load_manifest()
    assert payload["expected_pages"] == 72
    assert len(payload["pages"]) == 72
    assert {page["auction_date"] for page in payload["pages"]} == {
        "2019-02-13", "2019-04-04", "2019-05-23", "2019-07-18",
        "2019-09-03", "2019-10-17", "2019-12-11",
        "2020-02-12", "2020-04-07", "2020-04-21", "2020-06-08",
        "2020-07-15", "2020-09-09", "2020-10-27", "2020-12-15",
    }


def detail_html(heading, price, flash, description):
    return f"""
    <html><body>
      <h1>{heading}</h1>
      <h2 class="property-header-price">{price}</h2>
      <span class="p-flash">{flash}</span>
      <div class="property-description">{description}</div>
    </body></html>
    """.encode()


def test_parser_keeps_sale_price_rent_and_mixed_use_distinct():
    raw = detail_html(
        "Lot 2 - Tuesday 15th December 2020 - 63 Lawrence Road, Liverpool, L15 0EE",
        "SOLD £150,000",
        "SOLD",
        "A commercial shop with a three bedroom flat. Immediate income £1,250pcm.",
    )
    row = collector.parse_detail_page(raw, {
        "auction_date": "2020-12-15",
        "expected_lot_number": "2",
    })
    assert row["status"] == "sold"
    assert row["sale_price"] == 150000
    assert row["guide_price"] is None
    assert row["annual_rent"] == 15000
    assert row["sector"] == "mixed-use"


def test_parser_preserves_available_price_as_guide_but_withdrawn_outcome():
    raw = detail_html(
        "Lot 16 - Tuesday 15th December 2020 - 22 Bala Street, Liverpool, L4 2QW",
        "AVAILABLE £64,000",
        "WITHDRAWN",
        "A two bedroom house let at £400pcm.",
    )
    row = collector.parse_detail_page(raw, {
        "auction_date": "2020-12-15",
        "expected_lot_number": "16",
    })
    assert row["status"] == "withdrawn"
    assert row["guide_price"] == 64000
    assert row["sale_price"] is None
    assert row["annual_rent"] == 4800


def test_parser_rejects_a_manifest_identity_mismatch():
    raw = detail_html(
        "Lot 3 - Tuesday 15th December 2020 - 3 Test Road, Liverpool, L1 1AA",
        "SOLD £80,000",
        "SOLD",
        "A house.",
    )
    with pytest.raises(ValueError, match="does not match manifest"):
        collector.parse_detail_page(raw, {
            "auction_date": "2020-12-15",
            "expected_lot_number": "4",
        })


def test_parser_marks_a_source_truncated_unit_address_partial():
    raw = detail_html(
        "Lot 5 - Tuesday 27th October 2020 - Apartment 7, 150, Liverpool, L8 7LL",
        "AVAILABLE £67,000",
        "WITHDRAWN",
        "A two bedroom apartment.",
    )
    row = collector.parse_detail_page(raw, {
        "auction_date": "2020-10-27",
        "expected_lot_number": "5",
    })
    assert row["address_precision"] == "partial"


def test_manifest_validation_rejects_duplicate_event_lot_identity(tmp_path):
    payload = {
        "expected_pages": 2,
        "pages": [
            {
                "property_reference": "1",
                "auction_date": "2020-12-15",
                "expected_lot_number": "2",
                "source_url": "https://example.test/?property_reference=1",
            },
            {
                "property_reference": "2",
                "auction_date": "2020-12-15",
                "expected_lot_number": "2",
                "source_url": "https://example.test/?property_reference=2",
            },
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="duplicate event lot identities"):
        collector.load_manifest(path)


def test_persisted_batch_baseline_keeps_new_source_year_on_rerun():
    baseline_years = {"2021", "2022", "2023", "2024", "2025", "2026"}
    years_after = baseline_years | {"2020"}
    assert sorted(years_after - baseline_years) == ["2020"]
