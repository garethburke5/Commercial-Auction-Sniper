from datetime import date

import historical_corpus as corpus
from scripts import harvest_shepherd_deals_done as shepherd


def index_html():
    return """
    <div class="property-wrapper">
      <a href="/property/details/1/overlap-auction-property">
        <p class="item-cost">For Sale: £40,000 Guide price</p>
        <p class="lot-number">Lot No. 7</p><div class="unavailable-status">Sold</div>
        <p class="item-address">1 Historic Street, Ayr</p>
        <p class="item-size"><span>Auction Property</span><span>Retail</span></p>
      </a>
    </div>
    <div class="property-wrapper d-none">
      <a href="/property/details/2/new-auction-property">
        <p class="item-cost">For Sale: £50,000 - £60,000 Guide price</p>
        <p class="lot-number">Lot No. 8</p><div class="unavailable-status">Sold at Auction</div>
        <p class="item-address">2 New Street, Ayr</p>
        <p class="item-size"><span>Office</span><span>Auction Property</span></p>
      </a>
    </div>
    <div class="property-wrapper d-none">
      <a href="/property/details/3/not-auction"><p class="item-address">3 Let Street</p>
        <p class="item-size"><span>Office</span></p></a>
    </div>
    <button onclick="loadMore()">Load More</button>
    """.encode()


def detail_html(address, auction_date, lot, guide, status="SOLD", rent=None):
    rent_line = f"Current passing rent £{rent:,} per annum" if rent else ""
    return f"""
    <div class="property-details">
      <p class="property-lot">Lot No. {lot}</p><h1 class="property-address">{address}</h1>
      <div class="property-cost-size"><p class="item-cost">Auction</p>
        <p class="item-cost">For sale: £{guide:,} Guide price</p>
        <p class="item-size"><span>Auction Property</span><span>Retail</span>1,250 Sq Ft</p>
      </div>
      <p class="property-auction">Auction date: <span>{auction_date}</span></p>
      <div class="featured-bullets"><p class="bullet-item">Lot No {lot} - {status}</p>
        <p class="bullet-item">{rent_line}</p><p class="bullet-item">Guide Price £{guide:,}</p></div>
    </div>
    <div class="property-images-slider"><img src="/image-{lot}.jpg"></div>
    <p class="detail-description">**{status}** First-party property description. {rent_line}</p>
    <a href="/brochure-{lot}.pdf">Download brochure</a>
    """.encode()


def configure_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(corpus, "ROOT", tmp_path)
    monkeypatch.setattr(corpus, "DATA", tmp_path / "data/auction_history")
    monkeypatch.setattr(shepherd.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(shepherd.corpus, "DATA", tmp_path / "data/auction_history")


def test_index_denominator_filters_non_auction_deals():
    denominator, cards = shepherd.parse_index(index_html())
    assert denominator == 3
    assert [card["source_id"] for card in cards] == ["1", "2"]
    assert cards[1]["lot_number"] == "8"
    assert cards[1]["types"] == ["Office"]


def test_detail_keeps_guide_rent_and_outcome_distinct():
    _, cards = shepherd.parse_index(index_html())
    raw = detail_html("2 New Street, Ayr", "Thursday 4th December 2025", "8", 50000, "SOLD AT AUCTION", 9000)
    row = shepherd.parse_detail(cards[1], raw, {"response_sha256": "detail"})
    assert row["auction_date"] == "2025-12-04"
    assert row["guide_price"] == 50000
    assert row["guide_price_high"] is None
    assert row["sale_price"] is None
    assert row["annual_rent"] == 9000
    assert row["status"] == "sold at auction"
    assert row["floor_area"] == 1250


def test_batch_enriches_overlap_without_counting_it_twice(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    overlap = corpus.base_row(
        shepherd.SOURCE_NAME,
        "shepherd:2026-10-22",
        "2026-10-22",
        "7",
        "1",
        "https://www.shepherd.co.uk/property/details/1/overlap-auction-property",
    )
    overlap.update(
        address="1 Historic Street, Ayr",
        guide_price=40000,
        status="unknown",
        property_id="shepherd-detail:1",
        sector="commercial",
    )
    corpus.write_rows("shepherd-commercial/saved-properties", [overlap])

    payloads = {
        shepherd.INDEX_URL: index_html(),
        "https://www.shepherd.co.uk/property/details/1/overlap-auction-property": detail_html(
            "1 Historic Street, Ayr", "Thursday 22nd October 2026", "7", 40000, "SOLD", 12000
        ),
        "https://www.shepherd.co.uk/property/details/2/new-auction-property": detail_html(
            "2 New Street, Ayr", "Thursday 4th December 2025", "8", 50000, "SOLD AT AUCTION", 9000
        ),
    }
    monkeypatch.setattr(shepherd, "fetch", lambda url: payloads[url])
    summary = shepherd.run_collection(2, date(2026, 11, 14))

    assert summary["total_deal_cards"] == 3
    assert summary["auction_property_cards"] == 2
    assert summary["run_new_appearances"] == 1
    assert summary["run_duplicate_source_evidence_excluded"] == 1
    assert summary["run_enriched_existing_appearances"] == 1
    assert summary["run_new_outcomes_on_existing_appearances"] == 1
    assert summary["run_new_published_outcomes"] == 2
    assert summary["run_new_guide_prices"] == 1
    assert summary["run_new_sale_prices"] == 0
    assert summary["run_new_rents"] == 1
    assert summary["new_source_years"] == ["2025"]
    assert summary["source_event_dates"] == ["2025-12-04", "2026-10-22"]
    assert summary["deals_done_inventory_reconciled"] is True
    saved = list(corpus.iter_rows(corpus.DATA / "appearances/shepherd-commercial/saved-properties.jsonl.gz"))
    assert saved[0]["status"] == "sold"
    assert saved[0]["annual_rent"] == 12000
    assert len(saved[0]["additional_source_evidence"]) == 1
    deals = list(corpus.iter_rows(corpus.DATA / "appearances/shepherd-commercial/deals-done.jsonl.gz"))
    assert len(deals) == 1
    assert deals[0]["auction_date"] == "2025-12-04"

    rerun = shepherd.run_collection(2, date(2026, 11, 14))
    assert rerun["run_new_appearances"] == 0
    assert rerun["run_enriched_existing_appearances"] == 0
    assert rerun["run_new_published_outcomes"] == 0
