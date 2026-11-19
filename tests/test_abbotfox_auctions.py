from scripts import harvest_abbotfox_auctions as abbotfox


PAGE = """
<html><body>
<p>Map Showing Results 649 - 660 of 1475</p>
<div class="property result">
  <h3>Cliff Road, Cromer</h3>
  <p>£110,000</p>
  <p>For Sale By Unconditional Online Auction I Auction Ends 6th November 2026 at 10am
     SOLD FOR £165,000 abbotFox Auctions presents this two bedroom house.</p>
  <a href="/sales/properties-for-sale/property/5850-cliff-road-cromer">Read more...</a>
</div>
<div class="property result">
  <h3>Ordinary Road, Norwich</h3>
  <p>Guide price £250,000. abbotFox presents a detached house.</p>
  <a href="/sales/properties-for-sale/property/5849-ordinary-road">Read more...</a>
</div>
<p>Page 55 of 123</p>
</body></html>
"""


DETAIL = """
<html><body><main>
<h1>12 Cliff Road, Cromer, Norfolk NR27 9AB</h1>
<p>For Sale By Unconditional Online Auction | Auction Ends 6th November 2026 at 10am</p>
<p>Guide £110,000 - £120,000</p>
<p>SOLD FOR £165,000</p>
<p>The property is let at £9,600 per annum.</p>
</main></body></html>
"""


def test_page_parser_admits_only_explicit_individual_auction_cards():
    assert abbotfox.page_denominator(PAGE) == (1475, 123)
    rows, links = abbotfox.parse_page(PAGE, abbotfox.INDEX + "?start=648")
    assert links == 2
    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == "5850"
    assert row["auction_date"] == "2026-11-06"
    assert row["guide_price"] is None
    assert row["sale_price"] == 165000
    assert row["status"] == "sold"


def test_detail_keeps_guide_range_sale_and_rent_distinct():
    row = abbotfox.parse_page(PAGE, abbotfox.INDEX + "?start=648")[0][0]
    row = abbotfox.enrich_detail(row, DETAIL)
    assert row["address"] == "12 Cliff Road, Cromer, Norfolk NR27 9AB"
    assert row["auction_date"] == "2026-11-06"
    assert row["guide_price"] == 110000
    assert row["guide_price_high"] == 120000
    assert row["sale_price"] == 165000
    assert row["annual_rent"] == 9600


def test_dates_accept_both_published_orders_and_reject_ordinary_dates():
    assert abbotfox.exact_auction_date("Auction Ends Tuesday 15th December 2026 at 10am") == "2026-12-15"
    assert abbotfox.exact_auction_date("Auction Ends 10am December 15th 2026 at 10am") == "2026-12-15"
    assert abbotfox.exact_auction_date("Listed on 15th December 2026") is None


def test_removed_detail_does_not_destroy_index_evidence():
    row = {"auction_date": "2026-11-06", "address": "Cliff Road, Cromer"}
    html = "<html><body><h1>Property Not Found</h1><p>Sorry, no records were found.</p></body></html>"
    assert abbotfox.enrich_detail(row.copy(), html) == row
