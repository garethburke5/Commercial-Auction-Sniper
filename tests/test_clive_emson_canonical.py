from scripts.harvest_clive_emson_canonical import detail_fields, discover, parse_catalogue


INDEX = b"""
<ul><li><b>July 2026</b><span>Lots 1 - 3</span>
<a href='/properties/267/'>View Results</a></li></ul>
"""


CATALOGUE = b"""
<html><head><title>Results - 23rd July 2026</title></head><body>
<div class='lot activeLot' data-lot='1' data-auc='267'
 data-cathead='FREEHOLD PUBLIC HOUSE WITH FLAT' data-loc='Fowey - Cornwall'
 data-ceastatus='Sold' data-mainpic='one pic.jpg'>
 <a href='/properties/267/1/'><span class='lotNum'>LOT 1</span>
 <div class='statusBox'><label>SOLD</label><strong>&pound;580,000</strong></div></a>
</div>
<div class='lot activeLot' data-lot='3' data-auc='267'
 data-cathead='TWO BEDROOM MAISONETTE' data-loc='Romford' data-ceastatus='Withdrawn Prior'>
 <a href='/properties/267/3/'><span class='lotNum'>LOT 3</span>
 <div class='statusBox'><label>WITHDRAWN PRIOR</label></div></a>
</div>
</body></html>
"""


def test_discover_preserves_numbering_extent():
    auctions = discover(INDEX)
    assert auctions == [{
        "auction_id": "267",
        "url": "https://www.cliveemson.co.uk/properties/267/",
        "archive_label": "July 2026",
        "published_first_lot": 1,
        "published_last_lot": 3,
    }]


def test_parse_catalogue_banks_all_visible_rows_without_guessing_addresses():
    auction = discover(INDEX)[0]
    evidence = {"snapshot_path": "data/auction_history/sources/clive-emson/example.json.gz"}
    rows, state = parse_catalogue(CATALOGUE, auction, evidence)
    assert len(rows) == 2
    assert state["catalogue_complete"] is True
    assert state["numbering_gaps"] == [2]
    assert rows[0]["address"] is None
    assert rows[0]["locality"] == "Fowey - Cornwall"
    assert rows[0]["sale_price"] == 580000
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["status"] == "withdrawn prior"


def test_detail_parser_requires_matching_lot_and_date_and_recovers_address():
    raw = b"""
    <html><body><div class='lotDetailsHeader'>
      <h1 title='3/45631'><span>Lot 3</span><span>Freehold Ground Rents</span>
        <em>Auction Date: 23rd July 2026</em></h1>
      <h2>8-14 Copenhagen Road, Gillingham, Kent, ME7 4RY</h2>
      <div class='statusBox'><label>SOLD</label><strong>&pound;30,000</strong></div>
    </div>
    <div class='lotParams'><div class='row'>
      <div><span>Category</span>Ground Rents</div><div><span>Tenure</span>Freehold</div>
    </div></div>
    <div class='lotPropertyDetails'>Six flats sold on long leases.</div>
    <span data-hires='/Auc267/pics/45631-main.jpg'></span>
    </body></html>
    """
    fields = detail_fields(raw, "267", "3", "2026-07-23")
    assert fields["source_property_id"] == "45631"
    assert fields["address"] == "8-14 Copenhagen Road, Gillingham, Kent, ME7 4RY"
    assert fields["postcode"] == "ME7 4RY"
    assert fields["tenure"] == "Freehold"
    assert fields["sale_price"] == 30000
    assert fields["image_urls"] == ["https://www.cliveemson.co.uk/Auc267/pics/45631-main.jpg"]
