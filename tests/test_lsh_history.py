from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_lsh_results as lsh


FIXTURE = """
<html><body><div>Showing results 1 - 2 of 2</div>
<div class="lot-panel"><a href="/lot/details/381c1785-8681-4361-9653-9211dc113afd">
<img class="grid-img" src="/one.jpg"></a><div class="bottom-tag">London</div>
<h4 class="grid-address">1 High Street, London, SW1A 1AA</h4>
<div class="grid-tagline"><p>Freehold shop and upper parts</p></div>
<div class="grid-guideprice"><div class="row"><p>Result:</p><strong>Sold for £275,000</strong></div>
<div class="row"><p>Auction Date:</p><strong><time datetime="2023-05-18T11:05:00+00:00">18 May</time></strong></div></div></div>
<div class="lot-panel"><a href="/lot/details/28894983-a5cd-45cf-a760-772f3d14065d"></a>
<div class="bottom-tag">Leeds</div><h4 class="grid-address">Flat 2, 9 Road, Leeds, LS1 1AA</h4>
<div class="grid-tagline"><p>One bedroom flat</p></div>
<div class="grid-guideprice"><div class="row"><p>Result:</p><strong>No Bids</strong></div>
<div class="row"><p>Auction Date:</p><strong><time datetime="2023-05-18T11:10:00+00:00">18 May</time></strong></div></div></div>
</body></html>
"""


def test_denominator_and_rows_preserve_all_property_types():
    assert lsh.published_total(FIXTURE) == 2
    rows = lsh.parse_page(FIXTURE, 1, {"source_url": lsh.ARCHIVE_URL})
    assert len(rows) == 2
    assert rows[0]["lot_number"] is None
    assert rows[0]["auction_date"] == "2023-05-18"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 275000
    assert rows[0]["sector"] == "commercial"
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sector"] == "residential"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_stable_identity_is_source_lot_id_not_address():
    rows = lsh.parse_page(FIXTURE, 1, {})
    assert rows[0]["appearance_id"] == "LSH Auctions|eig-lot:381c1785-8681-4361-9653-9211dc113afd"
    assert rows[0]["source_auction_id"] == "lsh:2023-05-18"


def test_source_specific_result_labels_are_not_lost():
    assert lsh.status_and_price("Sale Agreed for £150,300") == ("sold", 150300)
    assert lsh.status_and_price("Sale Agreed Prior") == ("sold_prior", None)
    assert lsh.status_and_price("Postponed") == ("postponed", None)
