from scripts.harvest_loveitts_archive import (
    detail_date,
    enrich_detail,
    exact_date,
    parse_archive,
    parse_event,
    status_and_price,
)


ARCHIVE = """
<div class="auctions__item">
  <span class="auctions__item__date auctions__item__date--secondary">Tuesday 13th Oct 2026</span>
  <a href="/auctions/past-auctions/148">View properties</a>
</div>
<div class="auctions__item">
  <span class="auctions__item__date auctions__item__date--secondary">Tuesday 18th Aug 2026</span>
</div>
"""


EVENT = """
<h3>TUESDAY 13TH OCT 2026</h3>
<div class="property--sml">
  <a class="property--sml__content" href="/auctions/retail-unit-coventry-cv1-4ly">
    <span class="property--sml__ttl">Retail Unit, Coventry, West Midlands CV1 4LY</span>
    <span class="property--sml__subttl">Retail investment</span>
  </a>
  <span class="property--sml__price">Guide Price: £70,000 - £80,000</span>
  <span class="property--sml__status">SOLD AFTER</span>
  <span class="property--sml__img__link__img" style="background-image:url('/image.jpg')"></span>
</div>
"""


DETAIL = """
<main>
  <h1>Retail Unit, Coventry, West Midlands CV1 4LY</h1>
  <p>Guide Price: £70,000 - £80,000</p>
  <p>Auction TUESDAY 13TH OCT 2026 ENDING FROM 11:00 AM</p>
  <h4>DESCRIPTION</h4>
  <p>** SOLD AFTER AUCTION - £91,500 **</p>
  <p>Shop with flat above. The shop is let at £9,600 per annum.</p>
  <p>TENURE Freehold subject to the tenancy.</p>
  <h4>KEY FACTS</h4>
</main>
"""


def test_archive_retains_linked_events_and_reports_unlinked_dates():
    events, unlinked = parse_archive(ARCHIVE)
    assert events == [{
        "event_id": "148",
        "auction_date": "2026-10-13",
        "published_date": "Tuesday 13th Oct 2026",
        "event_url": "https://www.loveitts.co.uk/auctions/past-auctions/148",
        "source_position": 1,
    }]
    assert unlinked[0]["auction_date"] == "2026-08-18"
    assert "no retained property-page link" in unlinked[0]["reason"]


def test_event_card_preserves_guide_range_status_and_identity():
    event = {
        "event_id": "148",
        "auction_date": "2026-10-13",
        "event_url": "https://www.loveitts.co.uk/auctions/past-auctions/148",
    }
    rows, malformed = parse_event(EVENT, event, {"sha256": "abc"})
    assert malformed == []
    assert len(rows) == 1
    row = rows[0]
    assert row["appearance_id"] == "Loveitts|loveitts:148|retail-unit-coventry-cv1-4ly"
    assert row["guide_price"] == 70000
    assert row["guide_price_high"] == 80000
    assert row["status"] == "sold_after"
    assert row["sale_price"] is None
    assert row["sector"] == "commercial"


def test_detail_enrichment_requires_same_event_date_and_keeps_prices_distinct():
    event = {
        "event_id": "148",
        "auction_date": "2026-10-13",
        "event_url": "https://www.loveitts.co.uk/auctions/past-auctions/148",
    }
    row = parse_event(EVENT, event, {"sha256": "abc"})[0][0]
    enriched, observed = enrich_detail(DETAIL, row, {"sha256": "def"})
    assert observed == "2026-10-13"
    assert enriched["guide_price"] == 70000
    assert enriched["guide_price_high"] == 80000
    assert enriched["sale_price"] == 91500
    assert enriched["annual_rent"] == 9600
    assert enriched["status"] == "sold_after"
    assert enriched["sector"] == "mixed-use"


def test_date_and_outcome_parsers_do_not_turn_unsold_bid_into_sale():
    assert exact_date("Thursday 3rd Feb 2022") == "2022-02-03"
    assert detail_date("Auction Thursday 3rd February 2022") == "2022-02-03"
    assert status_and_price("UNSOLD - Last bid £125,000") == ("unsold", None)
    assert status_and_price("SOLD PRIOR - £175,000") == ("sold_prior", 175000)
