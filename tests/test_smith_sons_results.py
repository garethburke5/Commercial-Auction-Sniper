import pytest

from scripts.harvest_smith_sons_results import parse_archive, parse_catalogue, status_and_price


ARCHIVE = """
<html><body><h1>Past Auctions</h1><div class="auctions-list-past">
<div class="auction-list-item"><h3 class="auction-list-date"><a href="/auctionproperties/1248572">15th July 2026</a></h3>
<p>This auction had <strong>2</strong> properties</p></div></div></body></html>
"""

CATALOGUE = """
<html><body><h1>Auction 15th July 2026</h1><div>Results: 2 Properties</div>
<article class="property-item"><span class="lot-number-number">1</span>
<h2>£70,000 - £80,000</h2><p class="property-item-type">Garages</p>
<p class="property-address-list"><a href="/auctionproperties/land-at-backford-road">Land At Backford Road, Irby, CH61 2XH</a></p>
<p class="property-status">Sold £120,250</p><p>Land adjoining farmland.</p>
<a class="property-item-image"><img src="/uploads/land.jpg"></a></article>
<article class="property-item"><span class="lot-number-number">2A</span>
<h2>£40,000</h2><p class="property-item-type">Residential Investment</p>
<p class="property-address-list"><a href="/auctionproperties/47-parkside-road">47 Parkside Road, Birkenhead, CH42 5NY</a></p>
<p class="property-status">Sold After</p><p>Two bedroom house.</p></article>
</body></html>
"""


def test_archive_discovers_explicit_denominator_and_exact_date():
    rows = parse_archive(ARCHIVE)
    assert rows == [{
        "auction_id": "1248572", "auction_date": "2026-07-15", "published_lots": 2,
        "source_url": "https://www.smithandsons.net/auctionproperties/1248572",
    }]


def test_catalogue_reconciles_every_card_and_preserves_results():
    auction = parse_archive(ARCHIVE)[0]
    rows, state = parse_catalogue(CATALOGUE, auction, {"sha256": "abc"})
    assert state["catalogue_complete"] is True and state["lots_captured"] == 2
    assert rows[0]["appearance_id"] == "Smith & Sons|auction:1248572|lot:1|property:land-at-backford-road"
    assert rows[0]["address"] == "Land At Backford Road, Irby, CH61 2XH"
    assert rows[0]["guide_price"] == 70000 and rows[0]["guide_price_high"] == 80000
    assert rows[0]["sale_price"] == 120250 and rows[0]["status"] == "sold"
    assert rows[0]["image_urls"] == ["https://www.smithandsons.net/uploads/land.jpg"]
    assert rows[1]["lot_number"] == "2A" and rows[1]["status"] == "sold_after"
    assert rows[1]["sale_price"] is None


def test_catalogue_rejects_missing_published_rows():
    auction = {**parse_archive(ARCHIVE)[0], "published_lots": 3}
    with pytest.raises(ValueError, match="denominators disagree"):
        parse_catalogue(CATALOGUE, auction, {})


def test_status_parser_does_not_invent_non_sold_prices():
    assert status_and_price("Sold Prior £99,500") == ("sold_prior", 99500)
    assert status_and_price("Available £75,000") == ("available", None)
