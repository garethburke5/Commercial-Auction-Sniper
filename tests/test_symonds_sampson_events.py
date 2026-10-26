from scripts.harvest_symonds_sampson_events import discover_event_urls, parse_event


EVENT = b"""
<h4>Event Date &amp; Time: Thursday, 08 June 2023 2:00 PM</h4>
<a class="FeaturedGrid__item" href="/property/dwr00047b/ex13/axminster/pudleylake-road/land">
  <div class="status sold">Sold by Auction</div>
  <div data-bg="https://example.test/lot.jpg"></div>
  <h3>Pudleylake Road, Axminster, Devon, EX13</h3>
  <h3>Sold by Auction for &pound;226,000 Guide &pound;150,000 - &pound;175,000</h3>
</a>
"""


def test_discover_event_urls_is_ordered_and_deduplicated():
    raw = b'<a href="/event/property-auction-june-2023"></a><a href="/event/property-auction-june-2023"></a>'
    assert discover_event_urls([raw]) == [
        "https://auctions.symondsandsampson.co.uk/event/property-auction-june-2023"
    ]


def test_parse_event_preserves_exact_event_identity_and_prices():
    url = "https://auctions.symondsandsampson.co.uk/event/property-auction-june-2023"
    date, rows = parse_event(EVENT, url, {"source_url": url})
    assert date == "2023-06-08"
    assert len(rows) == 1
    row = rows[0]
    assert row["appearance_id"] == "Symonds & Sampson|event:property-auction-june-2023|listing:dwr00047b"
    assert row["source_auction_id"] == "symonds-sampson-event:property-auction-june-2023"
    assert row["address"] == "Pudleylake Road, Axminster, Devon, EX13"
    assert row["guide_price"] == 150000
    assert row["guide_price_high"] == 175000
    assert row["sale_price"] == 226000
    assert row["status"] == "sold"
    assert row["sector"] == "land"
