import pytest

from scripts.harvest_brown_co_results import parse_results, parse_status


HTML = """
<html><body><div class="cards">
<a href="https://brownandco.eigonlineauctions.com/lot/details/193314" class="card card--property card--property-auction">
  <img data-src="https://cdn.test/one.jpg">
  <div class="auction-date"><div class="ad-day">3</div></div>
  <div class="cp-loc">28 Sept 2026 - 29 Sept 2026</div>
  <div class="cp-long-address">1 High Street, Whissonsett, Dereham, Norfolk, NR20 5AP</div>
  <div class="cp-price-meta"><span>Sold for</span></div><div class="cp-price">£111,000</div>
</a>
<a href="https://brownandco.eigonlineauctions.com/lot/details/187052" class="card card--property card--property-auction">
  <div class="auction-date"><div class="ad-day">0</div></div>
  <div class="cp-loc">24 Aug 2026 - 25 Aug 2026</div>
  <div class="cp-long-address">Building Plot 1 Octagon Park, Church Field, Little Plumstead, Norwich, Norfolk, NR13 5FU</div>
  <div class="cp-price-meta"><span>Withdrawn</span></div><div class="cp-price">&nbsp;</div>
</a>
</div></body></html>
"""


def test_parse_results_keeps_stable_ids_dates_prices_and_lot_zero():
    rows = parse_results(HTML, {"sha256": "source"})
    assert len(rows) == 2
    first = rows[0]
    assert first["appearance_id"] == "Brown&Co|eig-lot:193314"
    assert first["source_auction_id"] == "brown-co:2026-09-29"
    assert first["auction_date"] == "2026-09-29"
    assert first["auction_start_date"] == "2026-09-28"
    assert first["lot_number"] == "3"
    assert first["postcode"] == "NR20 5AP"
    assert first["status"] == "sold" and first["sale_price"] == 111000
    assert first["record_quality"] == "address_record"
    assert rows[1]["lot_number"] == "0"
    assert rows[1]["status"] == "withdrawn" and rows[1]["sale_price"] is None


def test_status_preserves_undisclosed_sale_without_inventing_price():
    assert parse_status("Sold for", "Undisclosed") == ("sold", None)
    assert parse_status("Unsold", None) == ("unsold", None)
    assert parse_status(None, None) == ("unknown", None)


def test_empty_or_malformed_source_is_rejected():
    with pytest.raises(ValueError, match="no Brown&Co"):
        parse_results("<html></html>", {})
    with pytest.raises(ValueError, match="lacks identity"):
        parse_results('<a class="card--property-auction" href="https://brownandco.eigonlineauctions.com/lot/details/7"></a>', {})
