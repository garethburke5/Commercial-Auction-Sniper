from pathlib import Path
import gzip
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_sutton_kersh_results as sutton


ARCHIVE = """
<h2>2011</h2>
<p><a href="properties/listview/?section=auction&amp;auctionPeriod=49">May 11th 2011</a></p>
<h2>2026</h2>
<p><a href="properties/listview/?section=auction&amp;auctionPeriod=155">July 16th 2026</a></p>
"""

PAGE = """
<div class="propertyCount"><p>2 Properties</p></div>
<table class="auctionList"><tbody>
  <tr id="header_49_1">
    <td>1</td><td>9 High Street, Liverpool, Merseyside, L1 1AA</td>
    <td>L1 1AA</td><td>Sold for &pound;125,000</td><td><a href="/legal/one.pdf">Legal</a></td><td></td>
  </tr>
  <tr id="detail_49_1" class="hidden detailsRow"><td colspan="6">
    <a href="/properties/lot/340001/"><img class="lotImage" src="/one.jpg"></a>
    <p class="descriptionText">A mixed retail and residential investment.</p>
  </td></tr>
  <tr id="header_49_2">
    <td>2A</td><td>Land at Marsh Lane, Bootle, L20 1BB</td>
    <td>L20 1BB</td><td>Withdrawn</td><td></td><td></td>
  </tr>
  <tr id="detail_49_2" class="hidden detailsRow"><td colspan="6">
    <h3><a href="/properties/lot/340002/">Land at Marsh Lane</a></h3>
    <p class="descriptionText">Vacant development land.</p>
  </td></tr>
</tbody></table>
"""


def test_manifest_preserves_period_ids_and_exact_dates():
    rows = sutton.parse_manifest(ARCHIVE)
    assert rows == [
        {
            "period_id": "49",
            "auction_date": "2011-05-11",
            "published_date": "May 11th 2011",
            "source_auction_id": "sutton-kersh:49",
        },
        {
            "period_id": "155",
            "auction_date": "2026-07-16",
            "published_date": "July 16th 2026",
            "source_auction_id": "sutton-kersh:155",
        },
    ]


def test_page_rows_preserve_stable_property_identity_and_results():
    catalogue = sutton.parse_manifest(ARCHIVE)[0]
    rows = sutton.parse_page(PAGE, catalogue, {"source_url": "example"}, 0)
    assert sutton.published_total(PAGE) == 2
    assert len(rows) == 2
    assert rows[0]["appearance_id"] == "Sutton Kersh|period:49|property:340001"
    assert rows[0]["source_lot_id"] == "1"
    assert rows[0]["property_id"] == "340001"
    assert rows[0]["address"] == "9 High Street, Liverpool, Merseyside, L1 1AA"
    assert rows[0]["sale_price"] == 125000
    assert rows[0]["status"] == "sold"
    assert rows[0]["sector"] == "mixed-use"
    assert rows[0]["legal_pack_url"] == "https://www.suttonkersh.co.uk/legal/one.pdf"
    assert rows[1]["lot_number"] == "2A"
    assert rows[1]["status"] == "withdrawn"
    assert rows[1]["sector"] == "land"


def test_status_does_not_treat_available_price_as_sale_price():
    assert sutton.status("Available at £95,000") == "available"
    assert sutton.status("Sold Prior") == "sold_prior"
    assert sutton.status("Sold After") == "sold_after"
    assert sutton.status("Unsold") == "unsold"


def test_blank_published_lot_number_is_retained_as_null():
    page = PAGE.replace("<td>1</td><td>9 High Street", "<td></td><td>9 High Street", 1).replace(
        "Sold for &pound;125,000", "Guide Price: &pound;125,000+", 1
    )
    row = sutton.parse_page(page, sutton.parse_manifest(ARCHIVE)[0], {}, 0)[0]
    assert row["lot_number"] is None
    assert row["guide_price"] == 125000
    assert row["sale_price"] is None
    assert row["record_quality"] == "address_record"


def test_harvest_rejects_damaged_bank_before_network(tmp_path, monkeypatch):
    bank = tmp_path / "appearances/sutton_kersh/canonical.jsonl.gz"
    bank.parent.mkdir(parents=True)
    with gzip.open(bank, "wt", encoding="utf-8") as handle:
        handle.write('{"appearance_id": broken}\n')

    network_called = False

    def unexpected_network_call(*_args, **_kwargs):
        nonlocal network_called
        network_called = True
        raise AssertionError("network should not be touched for a damaged bank")

    monkeypatch.setattr(sutton.corpus, "DATA", tmp_path)
    monkeypatch.setattr(sutton, "get", unexpected_network_call)

    with pytest.raises(ValueError):
        sutton.harvest(catalogues=1, workers=1)
    assert network_called is False
