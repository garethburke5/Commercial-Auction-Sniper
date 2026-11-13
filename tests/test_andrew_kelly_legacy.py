from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from harvest_andrew_kelly_legacy import (
    archive_dates, parse_catalogue, parse_results, parse_rent, sector,
)


def test_catalogue_inventory_is_contiguous_and_preserves_guides():
    text = """
LOT 1 32-32a Withington Street, Heywood………………………………. £75,000 +
LOT 2 Land At Harrow Street, Rochdale………………………. £30,000 - £50,000
\f Guide Price: £75,000 + Description: Three bedroom house
\f Guide Price: £30,000 - £50,000 Site Description: Former garage site
"""
    rows = parse_catalogue(text, 2)
    assert [row["lot_number"] for row in rows] == ["1", "2"]
    assert (rows[0]["guide_price"], rows[0]["guide_price_high"]) == (75000, None)
    assert (rows[1]["guide_price"], rows[1]["guide_price_high"]) == (30000, 50000)
    assert [row["sector"] for row in rows] == ["residential", "land"]


def test_results_keep_available_separate_from_sale_price():
    text = """
1     32 – 32a Withington Street, Heywood   62,000   SOLD
2     Land At Harrow Street, Rochdale         -      AVAILABLE
3     88 Barnes Meadow, Littleoborough      56,000   SOLD PRIOR
"""
    rows = parse_results(text, 3)
    assert rows["1"]["status"] == "sold" and rows["1"]["sale_price"] == 62000
    assert rows["2"]["status"] == "available" and rows["2"]["sale_price"] is None
    assert rows["3"]["status"] == "sold_prior" and rows["3"]["sale_price"] == 56000


def test_rent_parser_requires_rental_context_and_preserves_range():
    assert parse_rent("anticipate a rental income of £450pcm") == (5400, None, "rental income of £450pcm")
    assert parse_rent("rental income in the region of £450-£495pcm")[:2] == (5400, 5940)
    assert parse_rent("service charge of £20 per month") == (None, None, None)


def test_commercial_and_residential_evidence_is_mixed_use():
    assert sector("24-26 Partington Street", "former shop with additional living accommodation") == "mixed-use"
    assert sector("The Caldermoor", "substantial former public house") == "commercial"


def test_archive_validation_requires_exact_dates_and_linked_catalogues(tmp_path, monkeypatch):
    html = """
    <a href='uploads/02-2011-Catalogue.pdf'>02-2011-Catalogue.pdf</a>
    <a href='uploads/Catalogue%20-%2020th%20April.pdf'>Catalogue - 20th April.pdf</a>
    <table><tr><td>23rd February 2011</td></tr><tr><td>20th April 2011</td></tr></table>
    """
    events = [
        {"auction_date": "2011-02-23", "catalogue_url": "https://x/uploads/02-2011-Catalogue.pdf"},
        {"auction_date": "2011-04-20", "catalogue_url": "https://x/uploads/Catalogue%20-%2020th%20April.pdf"},
    ]
    monkeypatch.setattr("harvest_andrew_kelly_legacy.corpus.DATA", tmp_path)
    monkeypatch.setattr("harvest_andrew_kelly_legacy.corpus.ROOT", tmp_path)
    evidence = archive_dates(html, "https://x/dates", events)
    assert evidence["basis"].startswith("first-party")
