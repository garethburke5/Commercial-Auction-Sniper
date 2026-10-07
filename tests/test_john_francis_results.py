import json

from scripts import harvest_john_francis_results as john


def test_discover_deduplicates_links_and_preserves_exact_archive_date():
    html = """
    <table class="auctions__table"><tbody><tr>
      <td><a href="/pages/lotlist?aid=166&amp;show=past">26/09/13</a></td>
      <td>Liberty Stadium</td><td>3 PM</td><td></td>
      <td><a href="/pages/lotlist?aid=166&amp;show=past">View Lots</a></td>
    </tr></tbody></table>
    """
    assert john.discover(html) == [{
        "source_id": "166",
        "auction_date": "2013-09-26",
        "venue": "Liberty Stadium",
        "source_url": "https://www.johnfrancis.co.uk/pages/lotlist?aid=166&show=past",
    }]


def test_parse_catalogue_banks_malformed_source_table_without_losing_rows():
    html = """
    <h4>List of properties for the auction held at Liberty Stadium on Thursday 26 September 2013 at 3 pm</h4>
    <table class="auctions__table"><tbody>
      <tr><td><a href="/pages/auction_property?lid=3628">1</a></td>
      <td><a href="/pages/auction_property?lid=3628">123 Sandy Road, Llanelli, SA15 4DH</a></td>
      <td><p>Sold for £68,000.</p></td>
      <td><a href="/pages/auction_property?lid=3628">View Details</a></td></tr>
      <td><a href="/pages/auction_property?lid=3629">2A</a></td>
      <td><a href="/pages/auction_property?lid=3629">Shop and Flat, 1 High Street, Swansea, SA1 1AA</a></td>
      <td><p>Withdrawn Prior to Auction.</p></td>
      <td><a href="/pages/auction_property?lid=3629">View Details</a></td>
    </tbody></table>
    """
    item = {"source_id": "166", "auction_date": "2013-09-26", "venue": "Liberty Stadium"}
    evidence = {"sha256": "abc", "snapshot_path": "source.json.gz"}
    rows, reconciliation = john.parse_catalogue(html, item, evidence)
    assert reconciliation["catalogue_complete"] is True
    assert reconciliation["visible_source_rows"] == 2
    assert [row["appearance_id"] for row in rows] == [
        "John Francis|john-francis:166|3628",
        "John Francis|john-francis:166|3629",
    ]
    assert rows[0]["lot_number"] == "1"
    assert rows[0]["postcode"] == "SA15 4DH"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 68000
    assert rows[1]["lot_number"] == "2A"
    assert rows[1]["sector"] == "mixed-use"
    assert rows[1]["status"] == "withdrawn"
    assert rows[1]["record_quality"] == "address_record"


def test_parse_catalogue_requires_matching_heading_date():
    html = """
    <h4>List of properties for the auction held at Liberty Stadium on Friday 27 September 2013 at 3 pm</h4>
    <table class="auctions__table"><tbody></tbody></table>
    """
    rows, reconciliation = john.parse_catalogue(
        html, {"source_id": "166", "auction_date": "2013-09-26", "venue": None}, {}
    )
    assert rows == []
    assert reconciliation["heading_date_matches_archive"] is False
    assert reconciliation["catalogue_complete"] is False


def test_archive_failure_uses_retained_states_and_resets_run_gains(tmp_path, monkeypatch):
    state_dir = tmp_path / "auctions/john-francis"
    state_dir.mkdir(parents=True)
    (state_dir / "166.json").write_text(json.dumps({
        "source_auction_id": "john-francis:166",
        "auction_date": "2013-09-26",
        "source_url": "https://www.johnfrancis.co.uk/pages/lotlist?aid=166&show=past",
        "catalogue_complete": True,
    }))
    appearance_dir = tmp_path / "appearances/john-francis"
    appearance_dir.mkdir(parents=True)
    (appearance_dir / "166.jsonl.gz").touch()
    row = {
        "appearance_id": "John Francis|john-francis:166|3628",
        "address": "123 Sandy Road, Llanelli, SA15 4DH",
        "sector": "residential",
        "status": "sold",
    }
    monkeypatch.setattr(john.corpus, "DATA", tmp_path)
    monkeypatch.setattr(john.corpus, "iter_rows", lambda path: iter([row]))
    monkeypatch.setattr(john, "get", lambda url: (_ for _ in ()).throw(RuntimeError("403 Forbidden")))

    summary = john.harvest()

    assert summary["archive_available"] is False
    assert summary["catalogue_discovery_basis"] == "saved_first_party_catalogue_states_after_archive_failure"
    assert summary["catalogues_discovered"] == 1
    assert summary["appearances_captured"] == 1
    assert summary["run_new_appearances"] == 0
    assert summary["run_new_address_records"] == 0
    assert summary["failures"] == [{
        "source_id": "archive",
        "source_url": john.ARCHIVE_URL,
        "error": "403 Forbidden",
    }]
    assert json.loads((tmp_path / "john_francis_collection.json").read_text())["run_new_appearances"] == 0
