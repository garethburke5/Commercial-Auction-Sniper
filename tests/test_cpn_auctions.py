from scripts import harvest_cpn_auctions as cpn
from scripts import harvest_harman_healy_results as shared


FIXTURE = """
<html><body>
<div>Showing results 1 - 3 of 3</div>
<div class="lot-panel"><div class="panel-title">Online: Auction Ended -
<time datetime="2026-04-22T14:25:00+00:00">22/04/2026 14:25</time></div>
<a href="/lot/details/11111111-1111-1111-1111-111111111111"></a>
<div class="list-info"><h3 class="list-address">Former White Lion Veterinary Clinic, South Hetton, DH6 2TU</h3>
<h4 class="lot-data-heading">Commercial Property</h4>
<p>Detached commercial property with development potential.</p></div>
<div class="list-guideprice">Result: <strong>Sold for £80,000</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Lot 3 | Auction Ended -
<time datetime="2025-05-30T13:06:00+00:00">30/05/2025 13:06</time></div>
<a href="/lot/details/22222222-2222-2222-2222-222222222222"></a>
<div class="list-info"><h3 class="list-address">33 Front Street, Leadgate, DH8 7SB</h3>
<h4 class="lot-data-heading">Betting shop investment</h4>
<p>New five year lease at £8,200 pa.</p></div>
<div class="list-guideprice">Result: <strong>Sold Prior</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Auction Ended -
<time datetime="2026-11-19T14:05:00+00:00">19/11/2026 14:05</time></div>
<a href="/lot/details/33333333-3333-3333-3333-333333333333"></a>
<div class="list-info"><h3 class="list-address">Elmsdale Social Club, Sutton Coldfield, B72 1JE</h3>
<h4 class="lot-data-heading">Development opportunity</h4><p>Freehold opportunity.</p></div>
<div class="list-guideprice">Result: <strong>No Bids</strong></div></div>
</body></html>
"""

DETAIL_FIXTURE = """
<html><body>
<h1>Lot 3 - 33 Front Street, Leadgate, DH8 7SB</h1>
<ul><li>Guide Price* : £50,000+</li></ul>
<p>New five year lease at a rebased rent of £8,200 pa.</p>
<p>Minimum Opening Bid: £45,000</p>
</body></html>
"""


def test_cpn_configuration_uses_search_grid_and_detail_enrichment():
    original = (
        shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER,
        shared.SLUG, shared.OPERATOR_METADATA, shared.ENRICH_DETAILS,
    )
    try:
        cpn.configure_cpn()
        assert shared.ARCHIVE_URL == "https://auctions.thecpn.co.uk/search"
        assert shared.AUCTIONEER == "CPN Auctions"
        assert shared.SLUG == "cpn-auctions"
        assert shared.ENRICH_DETAILS is True
        assert shared.OPERATOR_METADATA["trading_name_aliases"] == ["CPN"]
        assert shared.OPERATOR_METADATA["trading_name_aliases_counted_separately"] is False
    finally:
        (
            shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER,
            shared.SLUG, shared.OPERATOR_METADATA, shared.ENRICH_DETAILS,
        ) = original


def test_cpn_cards_preserve_dates_outcomes_prices_rent_and_sectors():
    original = (shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER, shared.SLUG)
    try:
        cpn.configure_cpn()
        rows = shared.parse_page(FIXTURE, 1, {"source_url": shared.ARCHIVE_URL})
    finally:
        shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER, shared.SLUG = original

    assert len(rows) == 3
    assert rows[0]["auction_date"] == "2026-04-22"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 80000
    assert rows[0]["guide_price"] is None
    assert rows[0]["sector"] == "commercial"
    assert rows[1]["status"] == "sold_prior"
    assert rows[1]["sale_price"] is None
    assert rows[1]["annual_rent"] == 8200
    assert rows[1]["sector"] == "commercial"
    assert rows[2]["status"] == "unsold"
    assert rows[2]["sale_price"] is None
    assert all(row["identity_method"] == "first_party_published_eig_lot_id" for row in rows)


def test_detail_parser_keeps_labelled_guide_and_rent_distinct_from_opening_bid():
    values = shared.detail_values(DETAIL_FIXTURE)
    assert values["guide_price"] == 50000
    assert values["annual_rent"] == 8200
    assert "£8,200 pa" in values["annual_rent_text"]
    assert shared.guide_price("Minimum Opening Bid: £45,000") is None
    assert shared.status_and_price("Guide Price*: £50,000") == ("unknown", None)
