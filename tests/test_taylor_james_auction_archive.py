from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_taylor_james_auction_archive as tj


FIXTURE = """
<html><body><div class="container-header"><h1><span class="month">Thursday 1st April 2021</span></h1></div>
<div class="property-block">
  <a class="property-link" href="/property/1-high-street-london-sw1a-1aa/"><span class="property-status">Sold - £275,000</span><img src="/one.jpg"></a>
  <h3>1 High Street, London, SW1A 1AA</h3><span class="property-price">£200,000 +</span>
  <span class="lot-number">7A</span><span class="feature">A Shop and Upper Parts with Rental Income of £20,000 per annum</span>
</div>
<div class="property-block">
  <a class="property-link" href="/property/2-road-leeds-ls1-1aa/"><span class="property-status">Withdrawn</span></a>
  <h3>2 Road, Leeds, LS1 1AA</h3><span class="property-price">£ +</span>
  <span class="lot-number">8</span><span class="feature">A One Bedroom Flat</span>
</div></body></html>
"""


def test_event_parser_preserves_prices_outcomes_rent_and_all_sectors():
    event_date, rows = tj.parse_event_page(FIXTURE, tj.BASE + "/auction/test/", {"sha256": "x"})
    assert event_date == "2021-04-01"
    assert len(rows) == 2
    assert rows[0]["lot_number"] == "7A"
    assert rows[0]["guide_price"] == 200000
    assert rows[0]["sale_price"] == 275000
    assert rows[0]["annual_rent"] == 20000
    assert rows[0]["status"] == "sold"
    assert rows[0]["sector"] in {"commercial", "mixed-use"}
    assert rows[1]["guide_price"] is None
    assert rows[1]["sale_price"] is None
    assert rows[1]["status"] == "withdrawn"
    assert rows[1]["sector"] == "residential"


def test_event_identity_includes_date_property_and_lot():
    _, rows = tj.parse_event_page(FIXTURE, tj.BASE + "/auction/test/", {})
    assert rows[0]["appearance_id"] == (
        "Taylor James Auctions|2021-04-01|property:1-high-street-london-sw1a-1aa|lot:7A"
    )
    assert rows[0]["original_url"].endswith("/property/1-high-street-london-sw1a-1aa/")


def test_outcome_does_not_infer_unpublished_achieved_price():
    assert tj.outcome("Sold Prior") == ("sold_prior", None)
    assert tj.outcome("Sold After") == ("sold_after", None)
    assert tj.outcome("Available - £50,000") == ("available", None)
    assert tj.outcome(None) == ("unknown", None)


def test_sitemap_admits_unique_first_party_event_urls_only():
    xml = b"""<urlset><url><loc>https://www.taylorjamesauctions.co.uk/auction/one/</loc></url>
    <url><loc>https://www.taylorjamesauctions.co.uk/property/not-an-event/</loc></url></urlset>"""
    assert tj.parse_sitemap(xml) == ["https://www.taylorjamesauctions.co.uk/auction/one/"]


def test_unlinked_card_and_missing_lot_are_preserved_without_inventing_values():
    fixture = """
    <html><body><div class="container-header"><h1><span class="month">Wednesday 19th October 2022</span></h1></div>
    <div class="property-block"><span class="property-status">Sold - £32,000</span>
    <h3>33 Blackburn Street, Workington, Cumbria CA14 2SS</h3><span class="property-price">£10,000 +</span>
    <span class="feature">A Two Bedroom Mid Terrace House</span></div></body></html>
    """
    event_date, rows = tj.parse_event_page(fixture, tj.BASE + "/auction/test/", {})
    assert event_date == "2022-10-19"
    assert len(rows) == 1
    assert rows[0]["lot_number"] is None
    assert rows[0]["original_url"] == tj.BASE + "/auction/test/"
    assert rows[0]["source_detail_url"] is None
    assert rows[0]["property_id"].startswith("unlinked-")
