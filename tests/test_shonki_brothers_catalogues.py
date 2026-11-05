import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shonki", ROOT / "scripts/harvest_shonki_brothers_catalogues.py"
)
shonki = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shonki)


def sample_catalogue():
    return """SHONKI BROTHERS
AUCTION
Wednesday 23 September 2026 at 2.30pm
\fAuction: Wednesday 23rd September 2026
Order of Sale
LOT              PROPERTY ADDRESS
Late Entry - A   Land at Example Farm, Leicester LE1 1AA
1                24 Example Street, Leicester LE2 2BB
IMPORTANT NOTICE
\f      LOT                     Land at Example Farm, Leicester LE1 1AA
       _A                      GUIDE PRICE: £100,000 - £105,000 PLUS VAT
LAND
Tenure:
Freehold.
\f        LOT                     24 Example Street, Leicester LE2 2BB
         1                      GUIDE PRICE: £120,000 - £125,000
RESIDENTIAL INVESTMENT
Current Rental Income                                                 12,000
"""


def test_exact_date_comes_from_cover():
    assert shonki.exact_auction_date(sample_catalogue()) == "2026-09-23"


def test_order_of_sale_and_lot_pages_reconcile():
    text = sample_catalogue()
    evidence = {"snapshot_path": "example.txt.gz"}
    rows = shonki.parse_lot_pages(text, "2026-09-23", "https://example/catalogue.pdf", evidence)
    assert shonki.parse_order_of_sale(text) == ["A", "1"]
    assert [row["lot_number"] for row in rows] == ["A", "1"]
    assert rows[0]["address"] == "Land at Example Farm, Leicester LE1 1AA"
    assert rows[0]["guide_price"] == 100000
    assert rows[0]["guide_price_high"] == 105000
    assert rows[1]["property_type"] == "RESIDENTIAL INVESTMENT"
    assert rows[1]["annual_rent"] == 12000
    assert rows[1]["sale_price"] is None


def test_non_property_pages_are_not_admitted():
    text = sample_catalogue() + "\fGuide Prices:\nGuide prices may change.\n"
    rows = shonki.parse_lot_pages(text, "2026-09-23", "https://example/catalogue.pdf", {})
    assert len(rows) == 2


def test_published_available_price_is_not_a_sale_price(monkeypatch):
    rows = shonki.parse_lot_pages(
        sample_catalogue(), "2026-09-23", "https://example/catalogue.pdf", {}
    )
    monkeypatch.setattr(shonki, "snapshot_outcomes", lambda seed: {"snapshot_path": "outcomes.txt.gz"})
    seed = {
        "outcomes": [
            {
                "auction_date": "2026-09-23",
                "lot_number": "01",
                "address": "24 Example Street, Leicester LE2 2BB",
                "result_text": "Available for £125,000",
                "detail_url": "https://example/unsold/24-example-street",
            }
        ]
    }
    assert shonki.apply_outcomes(rows, seed) == 1
    assert rows[1]["status"] == "unsold"
    assert rows[1]["available_price"] == 125000
    assert rows[1]["sale_price"] is None
