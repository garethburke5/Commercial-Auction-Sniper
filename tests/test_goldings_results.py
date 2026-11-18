from pathlib import Path
import sys
import json


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_goldings_results as goldings


ARCHIVE = """
<table><tr><td>Wednesday, 23 September 2026</td><td>8</td><td>100%</td>
<td>£1,003,500</td><td><a href="/auction/23-09-2026/">View Lots</a></td></tr></table>
"""

CATALOGUE = """
<div class="property-card" data-lotid="363703" data-wpid="31305">
  <a href="/lot/13-robeck-road-ipswich-suffolk-ip3-0hn/">
    <div class="property-card__meta-price"><h4>Sold for:</h4><span>£141,000</span></div>
    <div class="property-card__lot-no"><span>Lot</span><strong>1</strong></div>
  </a>
  <img data-src="/one.jpg">
  <div class="property-card__sold-flag">Sold</div>
  <div class="property-card__additional-meta">
    <div class="subtitle">Residential Investment</div>
    <div class="property-card__additional-meta__address">13 Robeck Road, Ipswich, Suffolk, IP3 0HN</div>
    <div class="property-card__additional-meta__tagline">Vacant two bedroom freehold investment</div>
  </div>
</div>
<div class="property-card" data-lotid="363704" data-wpid="31306">
  <a href="/lot/high-street-shop-norwich-nr1-1aa/">
    <div class="property-card__meta-price"><h4>Guide price:</h4><span>£90,000</span></div>
    <div class="property-card__lot-no"><span>Lot</span><strong>2A</strong></div>
  </a>
  <div class="property-card__additional-meta">
    <div class="subtitle">Commercial Investment</div>
    <div class="property-card__additional-meta__address">9 High Street, Norwich, NR1 1AA</div>
  </div>
</div>
"""


def test_archive_denominator_and_date_are_preserved():
    rows = goldings.parse_archive_rows(ARCHIVE)
    assert rows == [
        {
            "auction_date": "2026-09-23",
            "published_date": "Wednesday, 23 September 2026",
            "published_lots_offered": 8,
            "published_percent_sold": "100%",
            "published_total_raised": 1003500,
            "source_url": "https://www.goldingsauctions.co.uk/auction/23-09-2026/",
            "source_auction_id": "goldings:23-09-2026",
        }
    ]


def test_catalogue_cards_preserve_sold_and_unsold_property_types():
    catalogue = goldings.parse_archive_rows(ARCHIVE)[0]
    rows = goldings.parse_catalogue(CATALOGUE, catalogue, {"source_url": catalogue["source_url"]})
    assert len(rows) == 2
    assert rows[0]["appearance_id"] == "Goldings Auctions|2026-09-23|lot:363703"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 141000
    assert rows[0]["sector"] == "residential"
    assert rows[1]["lot_number"] == "2A"
    assert rows[1]["status"] == "unknown"
    assert rows[1]["guide_price"] == 90000
    assert rows[1]["sector"] == "commercial"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_catalogue_identity_is_scoped_to_exact_auction_date():
    catalogue = goldings.parse_archive_rows(ARCHIVE)[0]
    rows = goldings.parse_catalogue(CATALOGUE, catalogue, {})
    assert rows[0]["source_auction_id"] == "goldings:23-09-2026"
    assert rows[0]["source_lot_id"] == "363703"
    assert rows[0]["source_property_id"] == "31305"

def test_saved_catalogue_accepts_legacy_plain_json_with_gz_suffix(tmp_path, monkeypatch):
    source_url = "https://www.goldingsauctions.co.uk/auction/23-09-2026/"
    catalogue = {
        "source_url": source_url,
        "source_auction_id": "goldings:23-09-2026",
        "auction_date": "2026-09-23",
    }
    data_root = tmp_path / "data"
    state_dir = data_root / "auctions" / "goldings"
    state_dir.mkdir(parents=True)
    snapshot = tmp_path / "snapshots" / "legacy.json.gz"
    snapshot.parent.mkdir()
    snapshot.write_text(json.dumps({
        "html": CATALOGUE,
        "evidence": {"source_url": source_url, "legacy_encoding": "plain-json"},
    }))
    state_path = state_dir / f"{goldings.catalogue_slug(source_url)}.json"
    state_path.write_text(json.dumps({
        "source_url": source_url,
        "source_evidence": {"snapshot_path": "snapshots/structured-catalogue.json"},
        "result_source_evidence": {"snapshot_path": "snapshots/legacy.json.gz"},
    }))
    (tmp_path / "snapshots" / "structured-catalogue.json").write_text(json.dumps({
        "lot_records": [{"lot_number": "1"}],
        "evidence": {"source_url": "https://example.invalid/catalogue.pdf"},
    }))
    monkeypatch.setattr(goldings.corpus, "DATA", data_root)
    monkeypatch.setattr(goldings.corpus, "ROOT", tmp_path)

    html, returned_url, evidence = goldings.load_saved_catalogue(catalogue)

    assert html.decode("utf-8") == CATALOGUE
    assert returned_url == source_url
    assert evidence["legacy_encoding"] == "plain-json"

