import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "regional_catalogues",
    ROOT / "scripts" / "harvest_regional_property_auctioneers_catalogues.py",
)
regional = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(regional)


def test_manifest_batches_23_catalogues_and_267_properties():
    payload = regional.load_manifest()
    assert len(payload["events"]) == 23
    assert sum(event["expected_lots"] for event in payload["events"]) == 267
    assert {event["auction_date"][:4] for event in payload["events"]} == {
        "2018", "2019", "2020", "2021", "2022", "2023",
    }


def test_order_of_sale_is_the_only_row_denominator():
    fixture = """
Front cover 21st February 2018
\fOrder of sale
 Lot 1    1 High Street, Doncaster DN1 1AA             VACANT COMMERCIAL
 Lot 2    2 Green Road, Doncaster DN2 2BB              VACANT RESIDENTIAL
\fLOT 1 High Street, Doncaster DN1 1AA
 GUIDE PRICE £50,000+
 1 VACANT COMMERCIAL
\fLOT Stale Template House, Grimsby DN3 3CC
 GUIDE PRICE £10,000+
 17 VACANT RESIDENTIAL
"""
    rows = regional.parse_order_rows(fixture, 2)
    assert [row["lot_number"] for row in rows] == ["1", "2"]
    assert all("Stale Template" not in row["address"] for row in rows)
    enriched = regional.enrich_order_rows(rows, regional.detail_blocks(fixture))
    assert enriched[0]["guide_price"] == 50000
    assert enriched[1]["guide_price"] is None


def test_order_parser_rejects_noncontiguous_or_stale_tables():
    fixture = """Order of sale
 Lot 1    1 High Street, Doncaster DN1 1AA             VACANT COMMERCIAL
 Lot 3    3 Green Road, Doncaster DN2 2BB              VACANT RESIDENTIAL
"""
    try:
        regional.parse_order_rows(fixture, 2)
    except ValueError as exc:
        assert "not contiguous" in str(exc)
    else:
        raise AssertionError("noncontiguous source labels must be rejected")


def test_same_address_separate_lots_are_not_collapsed():
    fixture = """Order of sale
 Lot 1    Land At North Park Lane, Doncaster DN6 9JF    LAND
 Lot 2    Land At North Park Lane, Doncaster DN6 9JF    LAND
"""
    rows = regional.parse_order_rows(fixture, 2)
    assert [row["lot_number"] for row in rows] == ["1", "2"]
    assert rows[0]["address"] == rows[1]["address"]


def test_truncated_postcode_row_uses_published_sector_boundary():
    fixture = """Order of sale
 Lot 1    Workshops At R/O 37-39 Bentley Road, Doncaster DN5 GARAGE / LOCK UP
"""
    rows = regional.parse_order_rows(fixture, 1)
    assert rows[0]["address"].endswith("Doncaster DN5")
    assert rows[0]["property_type"] == "GARAGE / LOCK UP"


def test_guide_ranges_and_rents_stay_distinct():
    fixture = """
LOT 1 High Street, Doncaster DN1 1AA
GUIDE PRICE £50,000 - £60,000
1 COMMERCIAL INVESTMENT
Currently let at £7,500 per annum.
"""
    block = regional.detail_blocks(fixture)[0]
    assert block["guide_price"] == 50000
    assert block["guide_price_high"] == 60000
    assert block["annual_rent"] == 7500


def test_default_reuse_avoids_refreshing_reconciled_catalogues(tmp_path, monkeypatch):
    monkeypatch.setattr(regional.corpus, "DATA", tmp_path)
    states = tmp_path / "auctions" / regional.SLUG
    states.mkdir(parents=True)
    url = "https://example.invalid/catalogue.pdf"
    state = {
        "source_url": url,
        "source_auction_id": "regional-property-auctioneers:2020-01-01",
        "source_rows_complete": True,
        "lots_captured": 1,
    }
    regional.corpus.save_json(states / "2020-01-01.json", state)
    existing = [{"appearance_id": "one", "source_auction_id": state["source_auction_id"]}]
    reused = regional.reusable_states([{"source_url": url}], existing)
    assert reused[url][1] == existing
    assert regional.reusable_states([{"source_url": url}], existing, refresh_existing=True) == {}
