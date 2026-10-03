import pytest

from scripts.harvest_network_auctions import (
    discover_auctions,
    parse_catalogue,
    status_and_prices,
)


ARCHIVE = """
<div class="next-auction-content">Auction Date: 16 th March 2023 Time: 11am
  <a href="/auctions/next-auction/?auction_id=2252">View results</a>
</div>
<div class="future-auction-single">Auction Date: 27th April 2023
  <a href="/auctions/next-auction/?online_auction_id=74711">Online shell</a>
</div>
<div class="future-auction-single">Auction Date: 20th February 2020
  <a href="/auctions/next-auction/?auction_id=1514">View results</a>
</div>
"""

CATALOGUE = """
<h1>LOTS FOR AUCTION 16th March 2023</h1>
<div class="current-lots-single">
  <span class="lot-number">Lot 1</span><span class="lot-number past-lot-number">Sold</span>
  <a href="/property/?lot_id=199235"><div class="lot-info"><p><span>71 Quickley Lane</span><br>Rickmansworth, WD3 5AE</p></div></a>
  <p class="green-subtitle guide-price">£576,000</p>
</div>
<div class="current-lots-single">
  <span class="lot-number">Lot 3</span><span class="lot-number past-lot-number">Unsold</span>
  <a href="/property/?lot_id=199237"><div class="lot-info"><p><span>4 Radnor Court</span><br>Faringdon, SN7 7TB</p></div></a>
  <p class="green-subtitle guide-price">£120,000+</p>
</div>
<div class="current-lots-single">
  <span class="lot-number">Lot</span>
  <a href="/property/?lot_id=199243"><div class="lot-info"><p>Land at Unmapped Village</p></div></a>
  <p class="green-subtitle guide-price">Postponed to April 27th Auction</p>
</div>
"""


def test_archive_discovers_only_legacy_catalogues_and_ordinal_dates():
    assert discover_auctions(ARCHIVE) == [
        {
            "auction_id": "1514", "auction_date": "2020-02-20",
            "url": "https://www.networkauctions.co.uk/auctions/next-auction/?auction_id=1514",
        },
        {
            "auction_id": "2252", "auction_date": "2023-03-16",
            "url": "https://www.networkauctions.co.uk/auctions/next-auction/?auction_id=2252",
        },
    ]


def test_catalogue_banks_every_card_and_keeps_partial_lots():
    expected = discover_auctions(ARCHIVE)[1]
    state, rows = parse_catalogue(CATALOGUE, expected, {"sha256": "x"})
    assert state["catalogue_complete"] is True
    assert state["pagination_reconciled"] is True
    assert state["lots_captured"] == 3
    assert rows[0]["sale_price"] == 576000 and rows[0]["guide_price"] is None
    assert rows[0]["postcode"] == "WD3 5AE"
    assert rows[1]["status"] == "unsold" and rows[1]["guide_price"] == 120000
    assert rows[2]["status"] == "postponed"
    assert rows[2]["lot_number"] is None
    assert rows[2]["address"] is None and rows[2]["record_quality"] == "partial_lot"
    assert len({row["appearance_id"] for row in rows}) == 3


def test_status_and_price_semantics_are_not_conflated():
    assert status_and_prices("Sold", "£576,000") == ("sold", 576000, None)
    assert status_and_prices("Sold", "SOLD PRIOR") == ("sold_prior", None, None)
    assert status_and_prices("Unsold", "£120,000+") == ("unsold", None, 120000)
    assert status_and_prices("", "Postponed to April 27th Auction") == ("postponed", None, None)
    assert status_and_prices("No Bids", "£85,000+") == ("no_bids", None, 85000)


def test_duplicate_first_party_lot_ids_are_rejected():
    expected = discover_auctions(ARCHIVE)[1]
    duplicate = CATALOGUE.replace("lot_id=199237", "lot_id=199235")
    with pytest.raises(ValueError, match="duplicate first-party lot IDs"):
        parse_catalogue(duplicate, expected, {"sha256": "x"})
