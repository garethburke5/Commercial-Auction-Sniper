from scripts import harvest_swift_property_auctions as swift


def test_discover_uses_exact_archive_date_and_denominator():
    html = """
    <article class="date-card"><p>Tuesday 16 July 2024<br>15 lots · 5 sold</p>
    <a href="/previous-auctions/60309" aria-label="View results of the 16th July 2024 auction">View</a></article>
    """
    assert swift.discover(html) == [{
        "source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 15,
        "source_url": "https://www.swiftpropertyauctions.co.uk/previous-auctions/60309",
    }]


def test_parse_catalogue_preserves_result_and_full_address():
    html = """
    <h1>16th July 2024</h1>
    <article class="auction-lot x-result-lot" data-result="sold">
      <a class="auction-lot-photo" href="/lots/250305"><img src="https://cdn.example/one.jpg">
        <span class="auction-lot-badge">Lot 1A</span>
        <div class="auction-guide"><span>Guide price</span><strong>£125,000+</strong></div></a>
      <div class="auction-lot-content"><p class="sr-only">Result: SOLD for £141,000</p>
        <h3><a href="/lots/250305">17 Burnham Crescent</a></h3>
        <p class="auction-lot-location">Dartford, DA1 5BA</p>
        <p class="auction-lot-summary">A two bedroom ground floor garden maisonette</p></div>
      <a href="https://legaldocuments.eigroup.co.uk/showbyid/123">Legal Pack</a>
    </article>
    """
    item = {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 1}
    rows, reconciliation = swift.parse_catalogue(html, item, {"sha256": "abc"})
    assert reconciliation["catalogue_complete"] is True
    assert rows[0]["appearance_id"] == "Swift Property Auctions|swift:60309|250305"
    assert rows[0]["lot_number"] == "1A"
    assert rows[0]["address"] == "17 Burnham Crescent, Dartford, DA1 5BA"
    assert rows[0]["postcode"] == "DA1 5BA"
    assert rows[0]["guide_price"] == 125000
    assert rows[0]["sale_price"] == 141000
    assert rows[0]["status"] == "sold"
    assert rows[0]["sector"] == "residential"


def test_parse_catalogue_rejects_denominator_or_date_mismatch():
    html = '<h1>17th July 2024</h1><article class="auction-lot x-result-lot"></article>'
    rows, reconciliation = swift.parse_catalogue(
        html, {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 2}, {}
    )
    assert rows == []
    assert reconciliation["heading_date_matches_archive"] is False
    assert reconciliation["catalogue_complete"] is False


def test_withdrawn_and_postponed_cards_are_banked_outside_offered_denominator():
    def card(lot, source_id, status):
        return f'''<article class="auction-lot x-result-lot" data-result="{status}">
        <span class="auction-lot-badge">Lot {lot}</span>
        <h3><a href="/lots/{source_id}">{lot} High Street</a></h3>
        <p class="auction-lot-location">York YO1 1AA</p></article>'''
    html = '<h1>16th July 2024</h1>' + card(1, 101, 'sold') + card(2, 102, 'withdrawn') + card(3, 103, 'postponed')
    rows, reconciliation = swift.parse_catalogue(
        html, {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 1}, {}
    )
    assert [row["status"] for row in rows] == ["sold", "withdrawn", "postponed"]
    assert reconciliation["visible_source_rows"] == 3
    assert reconciliation["published_denominator_basis"] == (
        "visible lots excluding withdrawn and postponed outcomes"
    )
    assert reconciliation["visible_rows_in_published_denominator"] == 1
    assert reconciliation["visible_rows_outside_published_denominator"] == 2
    assert reconciliation["catalogue_complete"] is True


def test_retained_snapshot_recovers_cards_removed_from_current_page(tmp_path, monkeypatch):
    monkeypatch.setattr(swift.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(swift.corpus, "DATA", tmp_path / "data/auction_history")
    item = {"source_id": "60309", "auction_date": "2024-07-16", "expected_lots": 1}
    earlier = '''<h1>16th July 2024</h1>
    <article class="auction-lot x-result-lot" data-result="sold"><span class="auction-lot-badge">Lot 1</span>
      <h3><a href="/lots/101">1 High Street</a></h3></article>
    <article class="auction-lot x-result-lot" data-result="postponed"><span class="auction-lot-badge">Lot 2</span>
      <h3><a href="/lots/102">2 High Street</a></h3></article>'''
    snapshot = tmp_path / "data/auction_history/sources/swift-property-auctions/auction-60309-old.json.gz"
    swift.corpus.save_gzip(snapshot, {
        "evidence": {"retrieved_at": "2024-07-16T12:00:00+00:00", "snapshot_path": str(snapshot)},
        "html": earlier,
    })
    current, _ = swift.parse_catalogue(
        earlier.replace(earlier[earlier.index('<article', earlier.index('<article') + 1):], ""),
        item, {"retrieved_at": "2024-07-17T12:00:00+00:00"},
    )
    recovered = swift.retained_snapshot_only_rows(item, current)
    assert len(recovered) == 1
    assert recovered[0]["source_lot_id"] == "102"
    assert recovered[0]["status"] == "postponed"
    assert recovered[0]["source_visibility_basis"].startswith("retained earlier")


def test_harvest_banks_valid_lots_but_does_not_clear_count_discrepancy(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(swift.corpus,'ROOT',tmp_path)
    monkeypatch.setattr(swift.corpus,'DATA',tmp_path/'data/auction_history')
    archive='<article class="date-card"><p>1 lot</p><a href="/previous-auctions/99" aria-label="16th July 2024">View</a></article>'
    def card(i):
        return f'<article class="auction-lot x-result-lot" data-result="sold"><span class="auction-lot-badge">Lot {i}</span><h3><a href="/lots/{i}">{i} High Street</a></h3><p class="auction-lot-location">York YO1 1AA</p><div class="auction-guide">£100,000</div><div class="auction-guide x-result-price">£110,000</div></article>'
    detail='<h1>16th July 2024</h1>'+card(1)+card(2)
    calls = []
    def fake_get(url):
        calls.append(url)
        return (archive if url == swift.ARCHIVE_URL else detail).encode(), url
    monkeypatch.setattr(swift, 'get', fake_get)

    result = swift.harvest(workers=1)
    assert result['run_new_appearances'] == 2 and not result['complete']
    assert result['failures'] == []
    assert len(result['reconciliation_discrepancies']) == 1
    state = json.loads(swift.state_path('99').read_text())
    assert state['lots_captured'] == 2 and not state['denominator_reconciled']
    assert not state['catalogue_complete'] and state['errors']
    assert state['incomplete_reason'] == 'published_archive_denominator_differs_from_visible_unique_rows'
    assert state['retry_policy'].startswith('retry only when')
    assert calls.count('https://www.swiftpropertyauctions.co.uk/previous-auctions/99') == 1

    second = swift.harvest(workers=1)
    assert second['run_new_appearances'] == 0
    assert second['failures'] == []
    assert len(second['reconciliation_discrepancies']) == 1
    assert calls.count('https://www.swiftpropertyauctions.co.uk/previous-auctions/99') == 1
