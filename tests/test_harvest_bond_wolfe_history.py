from scripts.harvest_bond_wolfe_history import (
    discover_auction_ids,
    parse_auction_page,
    parse_cards,
)


def test_archive_discovery_deduplicates_and_rejects_other_links():
    html = """
    <a href="/auction/1364/">13 March 2019</a>
    <a href="https://www.bondwolfe.com/auction/1364/">duplicate</a>
    <a href="/auction/3451/">10 September 2026</a>
    <a href="/auctions/properties/123-property-auction-birmingham/">lot</a>
    """
    assert discover_auction_ids(html) == ["1364", "3451"]


def test_auction_page_requires_exact_heading_id_and_nonce():
    html = """
    <select id="tjd-property-auction"><option value="3451">3451</option></select>
    <div class="AuctionDetails-datetime">Thursday 10th September 2026 @ 08:30AM</div>
    <script>var tjdPropertyAjax = {"ajaxnonce":"abc123"};</script>
    """
    assert parse_auction_page(html) == ("2026-09-10", "abc123")


def test_show_all_cards_preserve_residential_land_and_partial_fields():
    html = """
    <div class="Properties-cardWrap">
      <a class="PropertyCard" href="/auctions/properties/357116-property-auction-birmingham/">
        <div class="PropertyCard-image"><img src="https://cdn.example/one.jpg"></div>
        <span class="PropertyCard-tag">Sold</span>
        <span class="PropertyCard-detail-lotnum">Lot 1</span>
        <h5 class="PropertyCard-detail-description">Land Adjacent 142 Road, Birmingham, B33 0QG</h5>
        <p class="PropertyCard-detail-tagline">Freehold land in Birmingham</p>
        <div class="Badge"><span>Land/Development</span></div>
        <div class="PropertyCard-detail-price"><h5>Sold for £105,000</h5></div>
      </a>
    </div>
    <div class="Properties-cardWrap">
      <a class="PropertyCard" href="/auctions/properties/357117-property-auction-walsall/">
        <span class="PropertyCard-detail-lotnum">Lot 2</span>
        <h5 class="PropertyCard-detail-description">2 Example Street, Walsall, WS1 1AA</h5>
        <p class="PropertyCard-detail-tagline">Two bedroom house</p>
        <div class="Badge"><span>Residential Vacant</span></div>
        <div class="PropertyCard-detail-price"><h5>Guide price £50,000+</h5></div>
      </a>
    </div>
    """
    rows, exclusions = parse_cards(html, "3451", "2026-09-10")
    assert not exclusions
    assert len(rows) == 2
    assert rows[0]["property_type"] == "Land/Development"
    assert rows[0]["result_price_gbp"] == 105000
    assert rows[1]["property_type"] == "Residential Vacant"
    assert rows[1]["guide_price_gbp"] == 50000
    assert rows[1]["status"] == "UNSOLD"
    assert rows[1]["image_url"] is None


def test_unnumbered_later_sale_teaser_is_explicitly_excluded():
    html = """
    <div class="Properties-cardWrap">
      <a class="PropertyCard" href="/auctions/properties/95030-property-auction-tipton/">
        <h5 class="PropertyCard-detail-description">Land at Tipton, DY4 7TY</h5>
        <p class="PropertyCard-detail-tagline">To be offered in our 27th February 2020 Auction Sale</p>
        <div class="Badge"><span>Land/Development</span></div>
        <div class="PropertyCard-detail-price"><h5>Guide price TO BE CONFIRMED</h5></div>
      </a>
    </div>
    """
    rows, exclusions = parse_cards(html, "1378", "2019-12-11")
    assert not rows
    assert exclusions[0]["source_record_id"] == "bond-wolfe-property:95030"
    assert "future-auction teaser" in exclusions[0]["reason"]
