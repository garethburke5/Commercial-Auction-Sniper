import pytest

import scripts.harvest_clive_emson_canonical as clive
from scripts.harvest_clive_emson_canonical import (
    catalogue_inventory,
    detail_identity,
    detail_fields,
    discover,
    parse_date,
    parse_catalogue,
    roundup_article_rows,
    roundup_lot_links,
)


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


def test_inventory_does_not_guess_redirected_legacy_catalogues():
    assert catalogue_inventory(INDEX) == discover(INDEX)


def test_roundup_links_admit_only_exact_first_party_lot_routes():
    html = b"""
    <a href='/properties/231/101/'>Lot 101</a>
    <a href='https://www.cliveemson.co.uk/properties/231/5/'>Lot 5</a>
    <a href='/properties/231/'>Old catalogue</a>
    <a href='https://example.com/properties/231/7/'>Foreign</a>
    """
    assert roundup_lot_links(html, "https://www.cliveemson.co.uk/news/example/") == [
        {"auction_id": "231", "lot_number": "101",
         "url": "https://www.cliveemson.co.uk/properties/231/101/"},
        {"auction_id": "231", "lot_number": "5",
         "url": "https://www.cliveemson.co.uk/properties/231/5/"},
    ]


def test_roundup_article_rows_bank_only_explicit_partial_evidence():
    html = b"""
    <div class='CEoldArticle'><p>
    <h2><span>Mixed-use investment in Kent</span></h2>
    <span>A shop with a self-contained flat above was sold for &pound;337,750.</span>
    <a href='/properties/231/101/'><span>View Lot 101</span></a>
    <h2><span>Development land near Southampton</span></h2>
    <span>The freehold site attracted strong interest from a potential buyer.</span>
    <a href='/properties/231/102/'><span>View Lot 102</span></a>
    <a href='https://example.com/properties/231/103/'>Foreign lot</a>
    </p></div>
    """
    evidence = {
        "snapshot_path": "data/auction_history/sources/clive-emson/roundups/example.json.gz",
        "sha256": "abc",
    }
    rows = roundup_article_rows(
        html, "https://www.cliveemson.co.uk/news/february-2022-auction-roundup/",
        "2022-02", evidence,
    )

    assert set(rows) == {("231", "101"), ("231", "102")}
    sold = rows[("231", "101")]
    assert sold["auction_date"] is None
    assert sold["auction_month"] == "2022-02"
    assert sold["address"] is None
    assert sold["postcode"] is None
    assert sold["record_quality"] == "partial_lot"
    assert sold["source_auction_id"] == "clive-emson:231"
    assert sold["sale_price"] == 337750
    assert sold["status"] == "sold"
    assert sold["sector"] == "mixed-use"

    unknown = rows[("231", "102")]
    assert unknown["sale_price"] is None
    assert unknown["status"] == "unknown"
    assert unknown["sector"] == "land"


def test_legacy_heading_date_allows_separate_ordinal_element():
    assert parse_date("Wednesday 9 th February 2022, 11:00 AM") == "2022-02-09"


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
    assert detail_identity(raw) == ("3", "2026-07-23")
    assert fields["source_property_id"] == "45631"
    assert fields["address"] == "8-14 Copenhagen Road, Gillingham, Kent, ME7 4RY"
    assert fields["postcode"] == "ME7 4RY"
    assert fields["tenure"] == "Freehold"
    assert fields["sale_price"] == 30000
    assert fields["image_urls"] == ["https://www.cliveemson.co.uk/Auc267/pics/45631-main.jpg"]


def test_next_enrichment_skips_catalogue_with_only_terminal_identity_failures(monkeypatch, tmp_path):
    monkeypatch.setattr(clive.corpus, "DATA", tmp_path)
    for auction_id in ("252", "253"):
        row = clive.corpus.base_row(
            "Clive Emson", f"clive-emson:{auction_id}", "2024-09-18", "1", "1",
            f"https://www.cliveemson.co.uk/properties/{auction_id}/1/",
        )
        clive.corpus.write_rows(f"clive-emson/{auction_id}", [row])
        state = {"detail_enrichment_errors": []}
        if auction_id == "252":
            state["detail_enrichment_errors"] = [{
                "appearance_id": row["appearance_id"],
                "error": "ValueError: detail date '2024-10-03' does not match '2024-09-18'",
            }]
        clive.corpus.save_json(clive.state_path(auction_id), state)

    assert clive.next_enrichment_auction() == "253"



def test_enrich_batch_advances_past_terminal_identity_failure(monkeypatch):
    targets = iter(["252", "253", None])
    calls = []
    monkeypatch.setattr(clive, "next_enrichment_auction", lambda: next(targets))

    def fake_enrich(auction_id, workers, fail_on_failures):
        calls.append((auction_id, fail_on_failures))
        if auction_id == "252":
            return {
                "auction_id": auction_id,
                "selected": 1,
                "enriched": 0,
                "failures": [{"error": "ValueError: detail date does not match catalogue"}],
            }
        return {
            "auction_id": auction_id,
            "selected": 3,
            "enriched": 3,
            "failures": [],
        }

    monkeypatch.setattr(clive, "enrich_auction", fake_enrich)
    batches = clive.enrich_batch(4, workers=2)
    assert [item["auction_id"] for item in batches] == ["252", "253"]
    assert calls == [("252", False), ("253", False)]


def test_enrich_batch_stops_after_source_failure(monkeypatch):
    targets = iter(["252", "253"])
    calls = []
    monkeypatch.setattr(clive, "next_enrichment_auction", lambda: next(targets))

    def fake_enrich(auction_id, workers, fail_on_failures):
        calls.append(auction_id)
        return {
            "auction_id": auction_id,
            "selected": 100,
            "enriched": 0,
            "failures": [{"error": "HTTPError: 403 Client Error"}],
        }

    monkeypatch.setattr(clive, "enrich_auction", fake_enrich)
    with pytest.raises(SystemExit):
        clive.enrich_batch(4)
    assert calls == ["252"]
