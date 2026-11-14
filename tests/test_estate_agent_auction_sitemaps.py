from datetime import date

import historical_corpus as corpus
from scripts import harvest_estate_agent_auction_sitemaps as collector


def sitemap(*urls):
    body = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
    return f"<urlset>{body}</urlset>".encode()


def abbotfox_html(address, description, features, title="Property For Sale"):
    return f"""
    <html><head><title>{title}</title>
      <meta property="og:description" content="{description}">
    </head><body><h1>{address} Guide price £80,000</h1>
      <div class="eapow-mainaddress">{address}</div>
      <ul id="starItem"><li>{features}</li></ul>
    </body></html>
    """.encode()


def bramleys_html(address, body, status="For Sale", guide="£150,000"):
    return f"""
    <div class="property-details__header"><h1>2 bed House - Semi-Detached {status}
      <span>{address}</span></h1><div>Auction Guide {guide}</div></div>
    <div class="property-details__body">{body}</div>
    """.encode()


def evidence():
    return {"response_sha256": "detail", "source_url": "fixture"}


def configure_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(corpus, "ROOT", tmp_path)
    monkeypatch.setattr(corpus, "DATA", tmp_path / "data/auction_history")
    monkeypatch.setattr(collector.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(collector.corpus, "DATA", tmp_path / "data/auction_history")


def test_abbotfox_keeps_price_types_and_does_not_infer_missing_year():
    source = collector.SOURCES[0]
    dated = abbotfox_html(
        "Cliff Road Cromer NR27 0BU",
        "For Sale By Unconditional Online Auction I Auction Ends 6th November 2026 at 10amSOLD FOR £165,000abbotFox Auctions",
        "Guide £110,000-£120,000 Bidding ends 10am 6th November",
        "2 Bedroom Property Sold STC Cliff Road, Cromer",
    )
    row = collector.parse_abbotfox(
        source,
        "https://www.abbotfox.co.uk/sales/properties-for-sale/property/5818-cliff-road-cromer",
        dated,
        evidence(),
    )
    assert row["auction_date"] == "2026-11-06"
    assert row["guide_price"] == 110000
    assert row["guide_price_high"] == 120000
    assert row["sale_price"] == 165000
    assert row["status"] == "sold"
    assert row["postcode"] == "NR27 0BU"

    undated = abbotfox_html(
        "Church View Close Norwich NR7 8QA",
        "FOR SALE BY LIVESTREAM AUCTION ON WEDNESDAY 1ST NOVEMBER AT 11:00AM",
        "Semi-detached chalet",
        "3 Bedroom Property Sold STC Church View Close, Norwich",
    )
    row = collector.parse_abbotfox(
        source,
        "https://www.abbotfox.co.uk/sales/properties-for-sale/property/194-church-view-close",
        undated,
        evidence(),
    )
    assert row["auction_date"] is None
    assert row["guide_price"] == 80000
    assert "intentionally null" in row["auction_date_basis"]


def test_bramleys_rejects_generic_auction_boilerplate():
    source = collector.SOURCES[1]
    url = "https://www.bramleys.com/property-details/34916698/west-yorkshire/halifax/392"
    body = (
        "FOR SALE BY ONLINE AUCTION / GUIDE PRICE: £150,000 "
        "BIDDING OPENS: 12PM - Wednesday 7th October, 2026 "
        "BIDDING ENDS: 12PM - Thursday 8th October, 2026"
    )
    row = collector.parse_bramleys(
        source,
        url,
        bramleys_html("Saddleworth Road, Greetland, Halifax", body, "Sold Subject to Contract"),
        evidence(),
    )
    assert row["auction_date"] == "2026-10-08"
    assert row["guide_price"] == 150000
    assert row["status"] == "sold subject to contract"

    generic = bramleys_html(
        "Highfield Crescent, Meltham, Holmfirth",
        "The auction legal pack contains title extracts relating to the auction property.",
    )
    assert collector.parse_bramleys(source, url, generic, evidence()) is None


def test_batched_run_reports_past_future_and_undated_without_duplicates(monkeypatch, tmp_path):
    configure_tmp(monkeypatch, tmp_path)
    abbot, bramleys = collector.SOURCES
    abbot_undated = "https://www.abbotfox.co.uk/sales/properties-for-sale/property/194-church-view-close"
    abbot_future = "https://www.abbotfox.co.uk/sales/properties-for-sale/property/5849-fir-close"
    abbot_false = "https://www.abbotfox.co.uk/sales/properties-for-sale/property/999-private-sale"
    bram_past = "https://www.bramleys.com/property-details/34916698/west-yorkshire/halifax/392"
    bram_false = "https://www.bramleys.com/property-details/34844828/west-yorkshire/holmfirth/highfield"
    payloads = {
        abbot.sitemap_url: sitemap(abbot_undated, abbot_future, abbot_false),
        bramleys.sitemap_url: sitemap(bram_past, bram_false),
        abbot_undated: abbotfox_html(
            "Church View Close Norwich NR7 8QA",
            "FOR SALE BY LIVESTREAM AUCTION ON WEDNESDAY 1ST NOVEMBER AT 11:00AM",
            "Semi-detached chalet",
        ),
        abbot_future: abbotfox_html(
            "Fir Close Mundford Thetford IP26 5EE",
            "For Sale By Unconditional Online Auction I Auction Ends 25th November 2026 at 10am Guide £80,000 - £90,000",
            "Guide £80,000 - £90,000 Bidding ends 25th November",
        ),
        abbot_false: abbotfox_html(
            "Ordinary Road Norwich NR1 1AA", "Private treaty description", "No onward chain"
        ),
        bram_past: bramleys_html(
            "Saddleworth Road, Greetland, Halifax",
            "FOR SALE BY ONLINE AUCTION GUIDE PRICE: £150,000 BIDDING ENDS: 12PM - Thursday 8th October, 2026",
            "Sold Subject to Contract",
        ),
        bram_false: bramleys_html(
            "Highfield Crescent, Meltham, Holmfirth",
            "The auction legal pack contains title extracts relating to the auction property.",
        ),
    }
    monkeypatch.setattr(collector, "fetch", lambda url: payloads[url])
    summary = collector.run_collection(3, date(2026, 11, 14))
    assert summary["run_new_appearances"] == 3
    assert summary["run_new_dated_twenty_year_address_records"] == 1
    assert summary["run_new_future_dated"] == 1
    assert summary["run_new_undated"] == 1
    assert summary["run_new_guide_prices"] == 3
    assert summary["run_new_sale_prices"] == 0
    assert summary["new_source_years"] == [{"auctioneer": "Bramleys", "year": "2026"}]
    assert summary["inventories"]["abbotfox"]["property_detail_urls_checked"] == 3
    assert summary["inventories"]["bramleys"]["auction_property_pages"] == 1

    rerun = collector.run_collection(3, date(2026, 11, 14))
    assert rerun["run_new_appearances"] == 0
    assert rerun["run_new_future_dated"] == 0
    assert rerun["run_new_undated"] == 0

