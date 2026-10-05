import pytest

from scripts.harvest_smith_sons_results import (
    catalogue_identity,
    full_catalogue_url,
    parse_archive,
    parse_catalogue,
    status_and_price,
)


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


def test_catalogue_identity_recovers_date_and_denominator_from_retained_page():
    assert catalogue_identity(CATALOGUE, "https://www.smithandsons.net/auctionproperties/1248572?pp=50") == {
        "auction_id": "1248572", "auction_date": "2026-07-15", "published_lots": 2,
        "source_url": "https://www.smithandsons.net/auctionproperties/1248572",
    }
    assert full_catalogue_url("https://www.smithandsons.net/auctionproperties/1248572") == (
        "https://www.smithandsons.net/auctionproperties/1248572?pp=50"
    )


def test_catalogue_preserves_addressless_source_card_as_partial_lot():
    partial_html = CATALOGUE.replace(
        '<p class="property-address-list"><a href="/auctionproperties/47-parkside-road">'
        '47 Parkside Road, Birkenhead, CH42 5NY</a></p>',
        '<a class="more-details-btn" href="/auctionproperties/47-parkside-road">More Details</a>',
    )
    auction = parse_archive(ARCHIVE)[0]
    rows, state = parse_catalogue(partial_html, auction, {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert rows[1]["address"] is None and rows[1]["postcode"] is None
    assert rows[1]["original_url"].endswith("/47-parkside-road")
    assert rows[1]["record_quality"] == "partial_lot"


def test_catalogue_accepts_unambiguous_duplicate_displayed_lot_label():
    duplicate_html = CATALOGUE.replace(
        '<span class="lot-number-number">2A</span>',
        '<span class="lot-number-number">1</span>',
    )
    auction = parse_archive(ARCHIVE)[0]
    rows, state = parse_catalogue(duplicate_html, auction, {"sha256": "abc"})
    assert len(rows) == 2 and len({row["appearance_id"] for row in rows}) == 2
    assert state["duplicate_lot_labels"] == {"1": 2}


def test_date_parser_accepts_source_heading_without_ordinal_suffix():
    plain_heading = CATALOGUE.replace("Auction 15th July 2026", "Auction 15 July 2026")
    auction = parse_archive(ARCHIVE)[0]
    rows, state = parse_catalogue(plain_heading, auction, {"sha256": "abc"})
    assert len(rows) == 2 and state["auction_date"] == "2026-07-15"
