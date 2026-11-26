from scripts import harvest_brookvale_auctions as brookvale
from scripts import harvest_harman_healy_results as shared


FIXTURE = """
<html><body>
<div>Showing results 1 - 3 of 3</div>
<div class="lot-panel"><div class="panel-title">Online: Auction Ended -
<time datetime="2026-09-10T17:54:00+00:00">10/09/2026 17:54</time></div>
<a href="/lot/details/11111111-1111-1111-1111-111111111111"></a>
<div class="list-info"><h3 class="list-address">2 Harvey Road, Birmingham, B26 1TD</h3>
<h4 class="lot-data-heading">Mixed-use investment</h4>
<p>Ground-floor commercial premises with a flat, producing £12,000 per annum.</p></div>
<div class="list-guideprice">Result: <strong>Sale Agreed for £205,000</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Auction Ended -
<time datetime="2026-11-09T10:00:00+00:00">09/11/2026 10:00</time></div>
<a href="/lot/details/22222222-2222-2222-2222-222222222222"></a>
<div class="list-info"><h3 class="list-address">30 New Road, Birmingham, B47 5ND</h3>
<h4 class="lot-data-heading">Three bedroom house</h4><p>Residential property.</p></div>
<div class="list-guideprice">Result: <strong>No Bids</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Lot 1 | End Time -
<time datetime="2026-12-18T13:00:00+00:00">18/12/2026 13:00</time></div>
<a href="/lot/details/33333333-3333-3333-3333-333333333333"></a>
<div class="list-info"><h3 class="list-address">8 Darnley Road, Gravesend, DA11 0RU</h3>
<h4 class="lot-data-heading">Commercial unit</h4><p>Freehold commercial property.</p></div>
<div class="list-guideprice">Guide Price*: <strong>£160,000</strong></div></div>
</body></html>
"""


def test_brookvale_configuration_uses_complete_search_grid():
    original = (
        shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER,
        shared.SLUG, shared.OPERATOR_METADATA,
    )
    try:
        brookvale.configure_brookvale()
        assert shared.ARCHIVE_URL == "https://auction.brookvale.uk/search"
        assert shared.AUCTIONEER == "Brookvale Auctions"
        assert shared.SLUG == "brookvale-auctions"
        assert shared.OPERATOR_METADATA["partner_agents_not_counted_as_auctioneers"] is True
    finally:
        (
            shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER,
            shared.SLUG, shared.OPERATOR_METADATA,
        ) = original


def test_brookvale_cards_keep_results_guides_rent_and_future_dates_distinct():
    original = (shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER, shared.SLUG)
    try:
        brookvale.configure_brookvale()
        rows = shared.parse_page(FIXTURE, 1, {"source_url": shared.ARCHIVE_URL})
    finally:
        shared.BASE, shared.ARCHIVE_URL, shared.AUCTIONEER, shared.SLUG = original

    assert len(rows) == 3
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 205000
    assert rows[0]["guide_price"] is None
    assert rows[0]["annual_rent"] == 12000
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sale_price"] is None
    assert rows[2]["auction_date"] == "2026-12-18"
    assert rows[2]["guide_price"] == 160000
    assert rows[2]["sale_price"] is None
    assert rows[2]["status"] == "unknown"
    assert all(row["identity_method"] == "first_party_published_eig_lot_id" for row in rows)


def test_guide_parser_never_turns_opening_bid_into_guide_or_sale():
    assert shared.guide_price("Guide Price*: £480,000") == 480000
    assert shared.guide_price("Minimum Opening Bid: £160,000") is None
    assert shared.status_and_price("Guide Price*: £480,000") == ("unknown", None)
