from scripts import harvest_dedman_gray_results as dedman


def script(*fragments: str) -> str:
    def encoded(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')
    return "\n".join(f'document.write("{encoded(fragment)}");' for fragment in fragments)


def test_discover_deduplicates_archive_links_and_keeps_exact_dates():
    value = script(
        '<a href="http://dedmangray.co.uk/auction/?q=1&aid=40&tid=105"><b>13/02/2013</b></a>',
        '<a href="http://dedmangray.co.uk/auction/?q=1&aid=40&tid=105">13/02/2013</a>',
        '<a href="http://dedmangray.co.uk/auction/?q=1&aid=83&tid=105"><b>03/04/2013</b></a>',
    )
    assert dedman.discover(value) == [
        {"source_id": "40", "auction_date": "2013-02-13"},
        {"source_id": "83", "auction_date": "2013-04-03"},
    ]


def test_parse_catalogue_banks_complete_address_row_and_published_result():
    value = script(
        '<div>Results for property auction held on 13 February</div>',
        '<table class="lotdetails"><tr><td class="lotimagecol">'
        '<a href="https://example.test/lot-details.html?lid=1011&ClientID=33">'
        '<img src="https://example.test/1011.jpg"></a></td><td><table>',
        '<tr class="lotrow"><td class="lotnum">LOT:  1A</td><td class="lottag"></td></tr>',
        '<tr><td colspan="2" style="padding:5px 0px;">FREEHOLD SHOP AND FLAT</td></tr>',
        '<tr><td colspan="2"><span class="lotheader">Address:</span> '
        '1 High Street, Southend-on-Sea, Essex, SS1 1AA</td></tr>',
        '<tr><td colspan="2"><span class="lotheader">Result:</span> '
        'SOLD PRIOR FOR £120k</td></tr></table></td></tr></table>',
    )
    evidence = {"sha256": "abc", "snapshot_path": "source.json.gz"}
    rows, reconciliation = dedman.parse_catalogue(
        value, {"source_id": "40", "auction_date": "2013-02-13"}, evidence
    )
    assert reconciliation["catalogue_complete"] is True
    assert reconciliation["visible_source_rows"] == 1
    assert rows[0]["appearance_id"] == "Dedman Gray|dedman-gray:40|1011"
    assert rows[0]["lot_number"] == "1A"
    assert rows[0]["postcode"] == "SS1 1AA"
    assert rows[0]["sector"] == "mixed-use"
    assert rows[0]["status"] == "sold_prior"
    assert rows[0]["sale_price"] == 120000
    assert rows[0]["record_quality"] == "address_record"
    assert rows[0]["source_evidence"] == evidence


def test_parse_catalogue_refuses_mismatched_archive_date():
    value = script(
        '<div>Results for property auction held on 14 February</div>',
        '<table class="lotdetails"><tr><td><table>',
        '<tr><td class="lotnum">LOT: 1</td></tr>',
        '<tr><td><span class="lotheader">Address:</span> 1 High Street, SS1 1AA</td></tr>',
        '</table></td></tr></table>',
    )
    _, reconciliation = dedman.parse_catalogue(
        value, {"source_id": "40", "auction_date": "2013-02-13"}, {}
    )
    assert reconciliation["heading_date_matches_archive"] is False
    assert reconciliation["catalogue_complete"] is False


def test_parse_catalogue_accepts_lettered_and_zero_row_result_catalogues():
    lettered = script(
        '<div>Results for property auction held on 13 February</div>',
        '<table class="lotdetails"><tr><td><a href="https://example.test/?lid=2"></a><table>',
        '<tr><td class="lotnum">LOT: CL</td></tr>',
        '<tr><td><span class="lotheader">Address:</span> 2 High Street, SS1 1AA</td></tr>',
        '</table></td></tr></table>',
    )
    rows, reconciliation = dedman.parse_catalogue(
        lettered, {"source_id": "40", "auction_date": "2013-02-13"}, {}
    )
    assert reconciliation["catalogue_complete"] is True
    assert rows[0]["lot_number"] == "CL"

    empty = script('<div>Results for property auction held on 13 February</div>')
    rows, reconciliation = dedman.parse_catalogue(
        empty, {"source_id": "40", "auction_date": "2013-02-13"}, {}
    )
    assert rows == []
    assert reconciliation["catalogue_complete"] is True
