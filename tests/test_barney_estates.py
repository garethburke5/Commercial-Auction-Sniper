from scripts.harvest_barney_estates import (
    build_row,
    exact_auction_date,
    page_inventory,
)


def item(**overrides):
    value = {
        "id": 26765,
        "sale_by": "Auction",
        "link": "https://www.barneyestates.co.uk/property/example/",
        "title": {"rendered": "18 Blacksmiths Grove Fishtoft Boston PE21 0BF"},
        "excerpt": {"rendered": (
            "<p>Property to be sold by Auction on Wednesday 22nd July 2026.</p>"
            "<p>Generating income of £9,960.00 per annum.</p>"
        )},
        "features": [],
        "address_street": "18 Blacksmiths Grove",
        "address_two": "Fishtoft",
        "address_three": "Boston",
        "address_four": "",
        "address_postcode": "PE21 0BF",
        "department": "residential-sales",
        "property_type": "House",
        "tenure": "Freehold",
        "price_qualifier": "Guide Price",
        "price_actual": "80000",
        "price_formatted": "&pound;80,000",
        "availability": "Sold",
        "images": [],
        "date_gmt": "2026-07-01T18:23:42",
        "modified_gmt": "2026-07-02T18:23:42",
    }
    value.update(overrides)
    return value


def test_exact_date_requires_auction_event_language():
    assert exact_auction_date(
        "Property to be sold by Auction on Wednesday 22nd July 2026", "PE21 0BF"
    )[0] == "2026-07-22"
    assert exact_auction_date(
        "Black Friday: 50% reduced auction fees before Friday 27th November 2026", "SL3 0EH"
    )[0] is None
    assert exact_auction_date(
        "Lease expires 1st July 2030 and auction offers are invited", "WV10 8ET"
    )[0] is None


def test_stale_foreign_postcode_rejects_date():
    text = (
        "14 Overnhurst Court, Bristol BS16 5DR. "
        "41 Oldbury Court Road BS16 2JF to be sold via Public Auction Wednesday 5th August 2026."
    )
    assert exact_auction_date(text, "BS16 5DR")[0] is None


def test_row_preserves_guide_status_rent_and_null_sale_price():
    row, diagnostic = build_row(item(), [{"source_url": "https://example.test"}])
    assert diagnostic is None
    assert row["auction_date"] == "2026-07-22"
    assert row["address"] == "18 Blacksmiths Grove, Fishtoft, Boston, PE21 0BF"
    assert row["guide_price"] == 80000
    assert row["sale_price"] is None
    assert row["status"] == "sold"
    assert row["annual_rent"] == 9960
    assert row["source_published_at"] == "2026-07-01T18:23:42"
    assert row["appearance_id"] == "Barney Estates|barney-estates:26765"


def test_publication_date_never_becomes_auction_date():
    value = item(excerpt={"rendered": "<p>Call the Agent to discuss an auction bid.</p>"})
    row, diagnostic = build_row(value, [])
    assert row["auction_date"] is None
    assert diagnostic is not None


def test_non_auction_property_is_excluded():
    row, diagnostic = build_row(item(sale_by="Private Treaty"), [])
    assert row is None
    assert diagnostic is None


def test_page_inventory_reads_stable_post_ids_and_denominator():
    html = """
    <div data-elementor-type="loop-item" class="post-26765 e-loop-item-26765">
      <a href="/property/example/">Example</a>
    </div>
    <div class="e-load-more-anchor" data-max-page="25" data-page="1"></div>
    """
    rows, pages = page_inventory(html, "https://www.barneyestates.co.uk/properties/")
    assert rows == {"26765": "https://www.barneyestates.co.uk/property/example/"}
    assert pages == 25

