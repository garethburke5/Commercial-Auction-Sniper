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

LEGACY_SINGLE = """
LOT 6
Clifton GUIDE PRICE: £100K+++
Mr M Smith, Solicitors, 7 Queen Square, Bristol BS1 4JE.
Whatley Road, Clifton, Bristol BS8 2PS
A retirement apartment requiring updating.
SOLD £110K
"""

LEGACY_SHARED = """
Southville GUIDE PRICE: £250K+++
LOT 4
Albert Lodge, British Road, Southville BS3 3BW
Southville GUIDE PRICE: £150K+++
LOT 5
254 Coronation Road, Southville BS3 1RS
SOLD PRIOR
SOLD £172K
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


def test_manifest_uses_three_pdf_denominator_for_first_archive_year():
    links = "".join(
        f'<div class="well green-border-box">Month {i} 2010 Auction Results'
        f'<a href="/archivepdf/result-{i}.pdf">View Catalogue</a></div>'
        for i in range(3)
    )
    assert len(hm.manifest(links, 2010, "https://www.hollismorgan.co.uk/archive")) == 3


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


def test_legacy_single_lot_uses_printed_lot_without_guessing_source_postcode():
    rows, date = hm.parse_pages(
        ["Wednesday, 23rd February 2011", LEGACY_SINGLE],
        "hm-feb2011", "https://example/catalogue.pdf", {"sha256": "abc"}, 2011, 2,
    )
    assert date == "2011-02-23"
    assert len(rows) == 1
    assert rows[0]["lot_number"] == "6"
    assert rows[0]["address"] is None
    assert rows[0]["postcode"] is None
    assert rows[0]["record_quality"] == "partial_lot"
    assert rows[0]["guide_price"] == 100000
    assert rows[0]["sale_price"] == 110000
    assert rows[0]["property_id"] is None


def test_legacy_shared_page_preserves_lots_without_speculative_address_mapping():
    rows, _ = hm.parse_pages(
        ["Wednesday, 23rd February 2011", LEGACY_SHARED],
        "hm-feb2011", "https://example/catalogue.pdf", {}, 2011, 2,
    )
    assert {row["lot_number"] for row in rows} == {"4", "5"}
    assert all(row["address"] is None for row in rows)
    assert all(row["status"] == "unknown" for row in rows)
    assert all(row["record_quality"] == "partial_lot" for row in rows)


def test_archive_month_filters_next_auction_promotions_and_allows_unknown_day():
    pages = ["Wednesday, 23rd February 2011"]
    assert hm.auction_date(pages, 2010, 12) is None


def test_result_variants_are_not_inferred_beyond_source_text():
    assert hm.status_and_price("SOLD PRIOR £1m+") == ("sold_prior", 1000000)
    assert hm.status_and_price("SOLD POST AUCTION") == ("sold_after", None)
    assert hm.status_and_price("AVAILABLE BY PRIVATE TREATY") == ("available", None)
    assert hm.status_and_price(None) == ("unknown", None)
