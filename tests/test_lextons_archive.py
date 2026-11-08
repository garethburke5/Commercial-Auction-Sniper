from scripts import harvest_lextons_archive as lextons


def detail(body, *, title="12 High Street, Brighton", price="125000", status="Sold At Auction"):
    return f"""
    <html><head><meta property="og:title" content="Shop and Flat - Lextons" /></head>
    <body>
      <div class="property-headings">
        <h1><span itemprop="name">{title}</span></h1>
        <span itemprop="price" content="{price}">Auction Guide, £{int(price):,}</span>
        <span>Freehold</span><span class="sale-auction">{status}</span>
      </div>
      <div class="property-full-details">{body}<span itemprop="description">{body}</span></div>
    </body></html>
    """


def test_search_inventory_reconciles_pages_and_unique_property_links():
    html = """
      <ul class="pagination"><li><a href="/search/20.html?bid=4">20</a></li></ul>
      <a href="/property-details/123/sussex/brighton/high-street">one</a>
      <a href="/property-details/123/sussex/brighton/high-street">duplicate</a>
      <a href="/property-details/456/sussex/hove/church-road?x=1">two</a>
    """
    pages, urls = lextons.search_inventory(html)
    assert pages == 20
    assert urls == [
        "https://www.lextons.co.uk/property-details/123/sussex/brighton/high-street",
        "https://www.lextons.co.uk/property-details/456/sussex/hove/church-road",
    ]


def test_detail_preserves_exact_date_guide_rent_status_and_identity():
    html = detail(
        "Auction Date: 22nd September 2022 Mixed use shop and two bedroom flat. "
        "Rental income £18,000 per annum. Lease dated 1 January 1999."
    )
    row = lextons.parse_detail(
        html,
        "https://www.lextons.co.uk/property-details/31704503/east-sussex/brighton/high-street",
    )
    assert row["appearance_id"] == "Lextons Auctions Ltd|property:31704503"
    assert row["auction_date"] == "2022-09-22"
    assert row["guide_price"] == 125000
    assert row["sale_price"] is None
    assert row["annual_rent"] == 18000
    assert row["status"] == "sold"
    assert row["sector"] == "mixed-use"
    assert row["tenure"] == "Freehold"
    assert row["address"] == "12 High Street, Brighton"


def test_dedicated_date_wins_over_stale_narrative_and_non_auction_dates():
    html = detail(
        "Auction Date 22nd November 2022. Online Auction Date 14th October 2022. "
        "Lease from 1st January 1990 and planning consent 4th March 2019."
    )
    row = lextons.parse_detail(
        html,
        "https://www.lextons.co.uk/property-details/100/east-sussex/brighton/west-street",
    )
    assert row["auction_date"] == "2022-11-22"


def test_undated_page_is_banked_without_inventing_date_or_sale_price():
    html = detail(
        "Investment property. Lease dated 3rd May 2010. Planning consent dated 7th June 2018.",
        status="Sold At Auction",
    )
    row = lextons.parse_detail(
        html,
        "https://www.lextons.co.uk/property-details/101/east-sussex/brighton/queens-road",
    )
    assert row["auction_date"] is None
    assert row["auction_date_precision"] == "unknown"
    assert row["guide_price"] == 125000
    assert row["sale_price"] is None


def test_for_sale_by_auction_label_is_an_exact_date():
    html = detail(
        "For Sale By Auction 20th November 2026 Three bedroom house.",
        status="For Sale By Auction",
    )
    row = lextons.parse_detail(
        html,
        "https://www.lextons.co.uk/property-details/102/west-sussex/littlehampton/road",
    )
    assert row["auction_date"] == "2026-11-20"
    assert row["status"] == "available"
