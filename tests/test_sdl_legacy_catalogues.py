import gzip
import json

from scripts.harvest_sdl_legacy_catalogues import (
    discover_catalogues, load_saved_archive, normalise_terminal_state,
    parse_catalogue_cards, parse_catalogue_identity,
    reconcile_saved_terminal_blockers,
)


ARCHIVE = """
<html><body>
<a href="/catalogues/archive/">Archive</a>
<a href="/catalogues/may-2022/">May 2022</a>
<a href="/catalogues/january-2024-national-property-auction-catalogue/">January 2024</a>
<a href="/catalogues/december-2025/">December 2025</a>
<a href="/catalogues/january-2026/">January 2026</a>
</body></html>
"""


CATALOGUE = """
<html><body>
<h1>National Property Auction</h1>
<p>Thursday 31st January 2024 at 9:00am</p>
<a href="/auction/1237/national-property-auction-2024-01-31/">View all lots</a>
<section class="featured">
  <article>
    <p>Lot 100</p>
    <ul><li>Apartment 216, 15 Hatton Garden, Liverpool L3 2HA</li>
        <li>Guide price* £70,000+ (plus fees)</li></ul>
    <a href="/property/49099/apartment-for-auction-liverpool/">View more</a>
    <img src="/media/49099.jpg">
  </article>
  <article>
    <p>Lot 2A</p>
    <ul><li>Gospel Hall, Caledonian Road, Milton Keynes MK13 0AP</li>
        <li>Guide Price £25,000 - £30,000</li></ul>
    <a href="/property/48861/place-of-worship-for-auction-milton-keynes/">View more</a>
  </article>
</section>
</body></html>
"""


def test_archive_selects_only_pre_btg_retained_catalogues():
    found = discover_catalogues(ARCHIVE)
    assert [item["month_hint"] for item in found] == ["2022-05", "2024-01"]
    assert found[0]["url"] == "https://www.sdlauctions.co.uk/catalogues/may-2022/"


def test_catalogue_requires_one_exact_auction_identity():
    auction_id, auction_date = parse_catalogue_identity(
        CATALOGUE, "https://www.sdlauctions.co.uk/catalogues/january-2024/"
    )
    assert auction_id == "1237"
    assert auction_date == "2024-01-31"


def test_catalogue_identity_ignores_prior_auction_navigation_link():
    html = CATALOGUE.replace(
        '<a href="/auction/1237/national-property-auction-2024-01-31/">',
        '<a href="/auction/1200/national-property-auction-2023-12-14/">Prior auction</a>'
        '<a href="/auction/1237/national-property-auction-2024-01-31/">',
    )
    auction_id, auction_date = parse_catalogue_identity(
        html, "https://www.sdlauctions.co.uk/catalogues/january-2024/"
    )
    assert auction_id == "1237"
    assert auction_date == "2024-01-31"


def test_catalogue_month_and_dated_auction_link_override_publication_date():
    html = CATALOGUE.replace(
        "Thursday 31st January 2024 at 9:00am",
        "Article updated Monday 5th February 2024",
    ).replace(
        "</body>",
        '<a href="/auction/1200/national-property-auction-2023-12-14/">Prior auction</a>'
        "</body>",
    )
    auction_id, auction_date = parse_catalogue_identity(
        html,
        "https://www.sdlauctions.co.uk/catalogues/january-2024-national-property-auction-catalogue/",
    )
    assert auction_id == "1237"
    assert auction_date == "2024-01-31"


def test_featured_cards_become_strict_address_appearances():
    rows = parse_catalogue_cards(
        CATALOGUE,
        "https://www.sdlauctions.co.uk/catalogues/january-2024/",
        "1237", "2024-01-31", {"sha256": "catalogue"},
    )
    assert len(rows) == 2
    by_id = {row["property_id"]: row for row in rows}
    apartment = by_id["49099"]
    assert apartment["appearance_id"] == "SDL Property Auctions|auction:1237|property:49099"
    assert apartment["lot_number"] == "100"
    assert apartment["address"] == "Apartment 216, 15 Hatton Garden, Liverpool L3 2HA"
    assert apartment["postcode"] == "L3 2HA"
    assert apartment["guide_price"] == 70000
    assert apartment["record_quality"] == "address_record"
    hall = by_id["48861"]
    assert hall["lot_number"] == "2A"
    assert hall["guide_price"] == 25000
    assert hall["guide_price_high"] == 30000
    assert hall["sector"] in {"commercial", "unknown"}


def test_cards_without_stable_property_identity_are_not_admitted():
    html = CATALOGUE.replace(
        '/property/49099/apartment-for-auction-liverpool/',
        '/news/not-a-property/',
    ).replace(
        '/property/48861/place-of-worship-for-auction-milton-keynes/',
        '/search/',
    )
    try:
        parse_catalogue_cards(
            html, "https://www.sdlauctions.co.uk/catalogues/january-2024/",
            "1237", "2024-01-31", {},
        )
    except ValueError as exc:
        assert "no fully evidenced" in str(exc)
    else:
        raise AssertionError("identity-free catalogue cards were admitted")


def test_prose_property_link_does_not_capture_multiple_card_container():
    html = CATALOGUE.replace(
        '<section class="featured">',
        '<section class="featured">'
        '<p>Read about <a href="/property/49099/apartment-for-auction-liverpool/">'
        'this apartment</a> and the other featured opportunity.</p>',
    )
    rows = parse_catalogue_cards(
        html, "https://www.sdlauctions.co.uk/catalogues/january-2024/",
        "1237", "2024-01-31", {},
    )
    assert len(rows) == 2
    apartment = {row["property_id"]: row for row in rows}["49099"]
    assert apartment["lot_number"] == "100"
    assert apartment["address"] == "Apartment 216, 15 Hatton Garden, Liverpool L3 2HA"


def test_saved_archive_fallback_validates_immutable_snapshot(tmp_path):
    archive_bytes = ARCHIVE.encode()
    import hashlib
    evidence = {
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "snapshot_path": "saved/archive.json.gz",
    }
    snapshot = tmp_path / evidence["snapshot_path"]
    snapshot.parent.mkdir()
    with gzip.open(snapshot, "wt") as handle:
        json.dump({"evidence": evidence, "html": ARCHIVE}, handle)
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"archive_evidence": evidence}))
    html, loaded_evidence = load_saved_archive(summary, tmp_path)
    assert html == ARCHIVE
    assert loaded_evidence == evidence


def test_terminal_redirect_is_a_source_blocker_not_parser_failure():
    state = {
        "terminal_unavailable": True,
        "source_url": "https://www.sdlauctions.co.uk/catalogues/old/",
        "final_url": "https://www.sdlauctions.co.uk/catalogues/archive/",
        "incomplete_reason": "first-party catalogue page is no longer retained",
        "errors": ["ValueError: catalogue page has no exact auction date"],
    }
    normalised, changed = normalise_terminal_state(state)
    assert changed
    assert normalised["errors"] == []
    assert normalised["source_blocker"]["kind"] == "first_party_catalogue_retired"
    assert normalised["source_blocker"]["original_errors"] == state["errors"]
    assert normalised["terminal_unavailable"] is True


def test_terminal_reconciliation_updates_states_and_summary_without_rows(tmp_path, monkeypatch):
    state_dir = tmp_path / "auctions/sdl-property-auctions"
    state_dir.mkdir(parents=True)
    state = {
        "terminal_unavailable": True,
        "source_url": "https://www.sdlauctions.co.uk/catalogues/old/",
        "final_url": "https://www.sdlauctions.co.uk/buy-property/",
        "catalogue_complete": False,
        "source_rows_captured": 0,
        "denominator_reconciled": False,
        "errors": ["ValueError: catalogue page has no exact auction date"],
    }
    state_path = state_dir / "catalogues-old.json"
    state_path.write_text(json.dumps(state))
    summary_path = tmp_path / "sdl_property_auctions_collection.json"
    summary_path.write_text(json.dumps({
        "blocked_catalogues": {"catalogues-old": state},
        "failures": [{"catalogue_url": state["source_url"], "error": state["errors"][0]}],
    }))
    monkeypatch.setattr(
        "scripts.harvest_sdl_legacy_catalogues.corpus.save_json",
        lambda path, payload: path.write_text(json.dumps(payload)),
    )

    result = reconcile_saved_terminal_blockers(tmp_path)

    saved_state = json.loads(state_path.read_text())
    saved_summary = json.loads(summary_path.read_text())
    assert result["states_changed"] == 1
    assert result["appearance_rows_changed"] == 0
    assert saved_state["errors"] == []
    assert saved_state["denominator_reconciled"] is False
    assert saved_summary["failures"] == []
    assert saved_summary["catalogue_pages_blocked"] == 1
