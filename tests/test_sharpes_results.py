from scripts import harvest_sharpes_results as sharpes


def test_discover_requires_url_and_text_date_to_match():
    html = '<a href="previous-auction-properties.php?date=2018-02-06">6th February 2018</a>'
    assert sharpes.discover(html) == [{
        "source_id": "2018-02-06", "auction_date": "2018-02-06",
        "source_url": "https://www.sharpesauctions.co.uk/previous-auction-properties.php?date=2018-02-06",
    }]


def test_parse_catalogue_preserves_identity_prices_and_outcome():
    html = """
    <h3>PREVIOUS AUCTION - 6th February 2018</h3>
    <div class="products_table_items"><div class="products_table_items_box">
      <div class="products_table_thumb"><a href="/property/11-new-street-denholme-bd13-4ae/422">
        <img src="/photo.jpg"><div class="products_table_price">Guide | £30,000 + Sold For £39,500</div></a></div>
      <div class="products_table_items_lotnumber"><span>Lot </span>2</div>
      <div class="products_table_items_lotnumber"><span>*SOLD AT AUCTION*</span></div>
      <div class="products_table_title"><a href="/product-details.php?viewid=99">11 New Street Denholme BD13 4AE</a></div>
    </div></div>
    """
    rows, state = sharpes.parse_catalogue(html, {"source_id": "2018-02-06", "auction_date": "2018-02-06"}, {"sha256": "abc"})
    assert state["catalogue_complete"] is True
    assert rows[0]["appearance_id"] == "Sharpes Auctions|sharpes:2018-02-06|422"
    assert rows[0]["lot_number"] == "2"
    assert rows[0]["address"] == "11 New Street Denholme BD13 4AE"
    assert rows[0]["postcode"] == "BD13 4AE"
    assert rows[0]["guide_price"] == 30000
    assert rows[0]["sale_price"] == 39500
    assert rows[0]["status"] == "sold"


def test_parse_catalogue_rejects_heading_date_mismatch():
    rows, state = sharpes.parse_catalogue(
        '<h3>PREVIOUS AUCTION - 7th February 2018</h3><div class="products_table_items"></div>',
        {"source_id": "2018-02-06", "auction_date": "2018-02-06"}, {},
    )
    assert rows == []
    assert state["catalogue_complete"] is False


def test_unsold_is_not_misclassified_as_sold():
    assert sharpes.status_value("*UNSOLD LOT - REFER*") == "unsold"
