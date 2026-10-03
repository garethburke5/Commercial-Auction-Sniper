from scripts.harvest_barnett_ross_canonical import discover, parse_catalogue, status_and_prices


def test_archive_discovery_excludes_non_uk_and_preserves_duplicate_month_days():
    raw = b'''<a href="archivelist.php?a=202412&countryid=1&day=12">UK one</a>
    <a href="archivelist.php?a=202412&countryid=1&day=19">UK two</a>
    <a href="archivelist.php?a=200912&countryid=2&day=0">Spain</a>'''
    auctions = discover(raw)
    assert [item["key"] for item in auctions] == ["202412-12", "202412-19"]


def test_catalogue_rows_reconcile_and_keep_all_property_sectors():
    raw = b'''<div>Thursday, 22nd October 2026 Auction</div>
    <h2>10th September 2026 Auction Results:</h2><table>
    <tr><th>Lot</th><th>Address</th><th>Location</th><th>Result</th></tr>
    <tr onclick="document.location='/property.php?id=4872925'"><td>1</td>
      <td class="address">474-476 Fulham Road, London SW6 1BY</td><td>London SW6</td><td>Sold Prior</td></tr>
    <tr onclick="document.location='/property.php?id=4872936'"><td>2A</td>
      <td class="address">9 Residential Close, Harrow HA1 1AA</td><td>Harrow</td><td>\xc2\xa3881,000</td></tr>
    </table>'''
    rows, reconciliation = parse_catalogue(raw, {"key": "202609-10"}, {"source_url": "x"})
    assert reconciliation == {"auction_date": "2026-09-10", "visible_lot_rows": 2,
                              "distinct_property_ids": 2, "missing_property_id_lots": [],
                              "catalogue_complete": True}
    assert [row["source_lot_id"] for row in rows] == ["4872925", "4872936"]
    assert rows[1]["sale_price"] == 881000
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_linkless_legacy_row_uses_exact_auction_and_lot_identity():
    raw = b'''<p>Auction Date: 31st October 2002</p><table><tr>
    <td>A</td><td class="address">3 Shepherd Street, London W1J 7HL</td><td>Withdrawn</td>
    </tr></table>'''
    rows, reconciliation = parse_catalogue(
        raw, {"key": "200211-0"}, {"source_url": "https://example.test/catalogue"}
    )
    assert reconciliation["catalogue_complete"] is True
    assert reconciliation["missing_property_id_lots"] == []
    assert rows[0]["source_lot_id"] == "archive-row:a"
    assert rows[0]["identity_method"] == "auction_lot_number"
    assert rows[0]["property_id"] is None
    assert rows[0]["original_url"] == "https://example.test/catalogue"


def test_legacy_pdf_particulars_are_stable_source_identity():
    raw = b'''<p>Auction Date: 30th November 2011</p><table><tr
    onclick="window.open('details/201112/A.pdf')"><td>A</td>
    <td class="address">3 Shepherd Street, London W1J 7HL</td><td>Withdrawn</td>
    </tr></table>'''
    rows, reconciliation = parse_catalogue(raw, {"key": "201112-0"}, {})
    assert reconciliation["catalogue_complete"] is True
    assert rows[0]["source_lot_id"] == "details/201112/a.pdf"
    assert rows[0]["original_url"].endswith("/details/201112/A.pdf")


def test_result_semantics_remain_distinct():
    assert status_and_prices("Sold Prior") == ("sold prior", None, None)
    assert status_and_prices("Available at £375,000") == ("available", None, 375000)
    assert status_and_prices("£159,000") == ("sold", 159000, None)
    assert status_and_prices("£2.09M") == ("sold", 2090000, None)
    assert status_and_prices("£82.5K") == ("sold", 82500, None)
    assert status_and_prices("Withdrawn Prior - Refer") == ("withdrawn prior", None, None)
