from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_harman_healy_results as hh


FIXTURE = """
<html><body>
<div>Showing results 1 - 2 of 2</div>
<div class="lot-panel"><div class="panel-title">Online: Lot 7A | Auction Ended -
<time datetime="2023-05-18T11:05:00.0000000+00:00">18/05/2023 11:05</time></div>
<a href="/lot/details/381c1785-8681-4361-9653-9211dc113afd"><img class="list-image" src="/one.jpg"></a>
<div class="list-info"><h3 class="list-address">1 High Street, London, SW1A 1AA</h3>
<h4 class="lot-data-heading">Shop and upper parts</h4><p>A mixed-use investment.</p></div>
<div class="list-guideprice">Result: <strong>Sold for £275,000</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Lot 8 | Auction Ended -
<time datetime="2023-05-18T11:10:00.0000000+00:00">18/05/2023 11:10</time></div>
<a href="/lot/details/28894983-a5cd-45cf-a760-772f3d14065d"></a>
<div class="list-info"><h3 class="list-address">Flat 2, 9 Road, Leeds, LS1 1AA</h3>
<h4 class="lot-data-heading">One bedroom flat</h4><p>A leasehold flat.</p></div>
<div class="list-guideprice">Result: <strong>No Bids</strong></div></div>
</body></html>
"""


def test_denominator_and_rows_preserve_all_property_types():
    assert hh.published_total(FIXTURE) == 2
    rows = hh.parse_page(FIXTURE, 1, {"source_url": hh.ARCHIVE_URL})
    assert len(rows) == 2
    assert rows[0]["lot_number"] == "7A"
    assert rows[0]["auction_date"] == "2023-05-18"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 275000
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sector"] == "residential"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_stable_identity_is_source_lot_id_not_address():
    rows = hh.parse_page(FIXTURE, 1, {})
    assert rows[0]["appearance_id"] == "Harman Healy|eig-lot:381c1785-8681-4361-9653-9211dc113afd"
    assert rows[0]["source_auction_id"] == "harman-healy:2023-05-18"
