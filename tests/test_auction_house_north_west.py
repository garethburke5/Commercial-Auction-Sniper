from scripts.harvest_auction_house_north_west import (
    is_historical_outcome,
    pagination_extent,
    parse_page,
    result_details,
    same_source_identity,
    conflict_evidence,
    merge_republished_appearance,
)


HTML = """
<html><body>
<h3>Past online auction results for Auction House North West</h3>
<table>
<tr><th>Address</th><th></th><th>Auctioneer</th><th>Auction Ended</th><th>Guide</th><th>Result</th></tr>
<tr>
<td><a aria-label="Fernlea, Heworth Road, Washington, Tyne And Wear, NE37 2PY" href="https://online.auctionhouse.co.uk/lot/redirect/366263"></a></td>
<td>Fernlea, Heworth Road, Washington, Tyne And Wear, NE37 2PY</td>
<td>Auction House North West</td><td>29/09/2026 13:13</td><td>£85,000</td><td>Sold for: £101,000</td>
</tr>
<tr>
<td><a href="https://online.auctionhouse.co.uk/lot/redirect/364779">68 Lingmell, Washington, Tyne And Wear, NE37 1TT</a></td>
<td>68 Lingmell, Washington, Tyne And Wear, NE37 1TT</td>
<td>Auction House North West</td><td>29/09/2026 13:10</td><td>£50,000 - £60,000</td><td>Last Bid: £49,000</td>
</tr>
</table>
<a href="/northwest/auction/past-auctions?page=2">2</a>
<a href="/northwest/auction/past-auctions?page=13">»»</a>
</body></html>
"""


def test_pagination_extent_uses_last_page_link():
    assert pagination_extent(HTML) == 13


def test_rows_keep_source_identity_prices_and_exact_end_date():
    rows = parse_page(HTML, "https://www.auctionhouse.co.uk/northwest/auction/past-auctions",
                      "data/source.json.gz", "abc", "2026-10-03T00:00:00Z")
    assert len(rows) == 2
    sold, last_bid = rows
    assert sold["appearance_id"] == "Auction House North West|online:366263"
    assert sold["auction_date"] == "2026-09-29"
    assert sold["address"].startswith("Fernlea")
    assert sold["guide_price"] == 85000
    assert sold["sale_price"] == 101000
    assert sold["status"] == "sold"
    assert last_bid["guide_price"] == 50000
    assert last_bid["guide_price_high"] == 60000
    assert last_bid["sale_price"] is None
    assert last_bid["last_bid_price"] == 49000
    assert last_bid["status"] == "last_bid"


def test_result_states_are_not_forced_to_sold():
    assert result_details("Sold Prior")[0] == "sold_prior"
    assert result_details("Postponed")[0] == "postponed"
    assert result_details("Last Bid: £25,000")[0] == "last_bid"
    assert result_details("No Bids")[0] == "no_bids"


def test_future_pending_rows_are_not_historical_outcomes():
    assert not is_historical_outcome(
        {"auction_date": "2999-01-01", "status": "no_bids"}
    )
    assert is_historical_outcome(
        {"auction_date": "2999-01-01", "status": "sold_prior"}
    )

def test_identity_conflict_preserves_both_rows_and_is_not_a_match():
    retained = {
        "address": "1 Old Street, Manchester, M1 1AA",
        "auction_end_time": "2025-01-01T12:00:00",
        "auction_date": "2025-01-01",
        "source_url": "https://example.invalid/retained",
        "source_snapshot": "data/retained.json.gz",
    }
    current = {
        "address": "2 New Street, Liverpool, L1 1AA",
        "auction_end_time": "2026-01-01T12:00:00",
        "auction_date": "2026-01-01",
        "source_url": "https://example.invalid/current",
        "source_snapshot": "data/current.json.gz",
    }

    assert not same_source_identity(retained, current)
    evidence = conflict_evidence("366952", 2, retained, current)
    assert evidence["retained"]["address"] == retained["address"]
    assert evidence["current"]["address"] == current["address"]
    assert evidence["retained"]["source_snapshot"] != evidence["current"]["source_snapshot"]

def test_same_event_building_accepts_apostrophe_variant_and_preserves_guides():
    retained = {
        "address": "16 St. James Street, Brighton, East Sussex, BN2 1RF",
        "postcode": "BN2 1RF",
        "auction_end_time": "2026-10-06T12:39:00",
        "guide_price": 140000,
        "guide_text": "£140,000",
        "status": "no_bids",
        "source_evidence": {"snapshot_path": "data/retained.json.gz"},
    }
    current = {
        "address": "16 St. James's Street, Brighton, East Sussex, BN2 1RF",
        "postcode": "BN2 1RF",
        "auction_end_time": "2026-10-06T12:39:00",
        "guide_price": 119000,
        "guide_text": "£119,000",
        "status": "no_bids",
        "source_evidence": {"snapshot_path": "data/current.json.gz"},
    }

    assert same_source_identity(retained, current)
    merged, changed = merge_republished_appearance(retained, current)
    assert changed
    assert merged["guide_price"] == 119000
    assert [item["guide_price"] for item in merged["publication_variants"]] == [140000, 119000]
    assert [item["source_evidence"]["snapshot_path"] for item in merged["publication_variants"]] == [
        "data/retained.json.gz",
        "data/current.json.gz",
    ]

