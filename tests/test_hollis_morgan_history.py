from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import harvest_hollis_morgan_results as hm


FIRST = """
RESULTS ISSUE
Wednesday, 18TH NOVEMBER 2015
"""

SINGLE = """
St Pauls GUIDE PRICE: £80K+++
VIEW FULL DETAILS http://www.hollismorgan.co.uk/property/25853436/result_auction
124B City Road, St. Pauls,
BRISTOL BS2 8YQ
Flat for updating
LOT
1
SOLD £127K
"""

COMBINED = """
Brislington GUIDE PRICE: £75K+++
VIEW FULL DETAILS http://www.hollismorgan.co.uk/property/25233353/result_auction
LOT 14
Brislington GUIDE PRICE: £70K+++
VIEW FULL DETAILS http://www.hollismorgan.co.uk/property/25233310/result_auction
LOT 15
SOLD £75K
SOLD POST AUCTION
"""


def test_manifest_requires_six_distinct_first_party_result_pdfs():
    links = "".join(
        f'<div class="well green-border-box">Month {i} 2015 Auction Results'
        f'<a href="/archivepdf/result-{i}.pdf">View Catalogue</a></div>'
        for i in range(6)
    )
    rows = hm.manifest(links, 2015, "https://www.hollismorgan.co.uk/archive")
    assert len(rows) == 6
    assert rows[0]["pdf_url"].endswith("result-0.pdf")


def test_single_pdf_property_row_preserves_address_prices_and_outcome():
    rows, date = hm.parse_pages([FIRST, SINGLE], "hm-nov2015", "https://example/catalogue.pdf", {"sha256": "abc"})
    assert date == "2015-11-18"
    assert len(rows) == 1
    row = rows[0]
    assert row["property_id"] == "25853436"
    assert row["lot_number"] == "1"
    assert row["address"] == "124B City Road, St. Pauls, BRISTOL BS2 8YQ"
    assert row["postcode"] == "BS2 8YQ"
    assert row["guide_price"] == 80000
    assert row["sale_price"] == 127000
    assert row["status"] == "sold"
    assert row["record_quality"] == "address_record"


def test_combined_pdf_page_keeps_strict_distinct_partial_rows():
    rows, _ = hm.parse_pages([FIRST, COMBINED], "hm-nov2015", "https://example/catalogue.pdf", {})
    assert len(rows) == 2
    assert len({row["appearance_id"] for row in rows}) == 2
    assert {row["property_id"] for row in rows} == {"25233353", "25233310"}
    assert all(row["address"] is None for row in rows)
    assert all(row["lot_number"] is None for row in rows)
    assert all(row["record_quality"] == "partial_lot" for row in rows)


def test_result_variants_are_not_inferred_beyond_source_text():
    assert hm.status_and_price("SOLD PRIOR £1m+") == ("sold_prior", 1000000)
    assert hm.status_and_price("SOLD POST AUCTION") == ("sold_after", None)
    assert hm.status_and_price("AVAILABLE BY PRIVATE TREATY") == ("available", None)
    assert hm.status_and_price(None) == ("unknown", None)
