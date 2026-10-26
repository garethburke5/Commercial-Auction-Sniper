from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_robinson_hall_results as rh


ARCHIVE = """
<table>
 <tr><th>Date</th><th>Lots Offered</th><th>Percent Sold</th><th>Total Raised</th></tr>
 <tr><td><a href="results.aspx?a=384&amp;c=rbh&amp;au=135951">Wednesday, 14 October 2026</a></td>
     <td>32</td><td>79%</td><td>£3,852,000</td></tr>
 <tr><td><a href="results.aspx?a=384&amp;c=rbh&amp;au=92155">Wednesday, 4 December 2024</a></td>
     <td>17</td><td>89%</td><td>£3,503,500</td></tr>
</table>
"""

RESULT = """
<table class="auctiondetails"><tr><td>Auction Date</td><td>Wednesday, 14 October 2026</td></tr></table>
<table class="lot-table sortable">
 <tr><th>Lot No.</th><th>Address</th><th>Result</th></tr>
 <tr class="lot-row"><td class="lotnum"><a href="LotDetails.aspx?LotID=1418663&amp;a=384&amp;c=rbh">1</a></td>
  <td><a href="LotDetails.aspx?LotID=1418663&amp;a=384&amp;c=rbh">Irthlingborough Town Band Club, 104 Victoria Street, Wellingborough, NN9 5RG</a></td>
  <td>Sold for £206,000.</td></tr>
 <tr class="lot-alt-row"><td class="lotnum"><a href="LotDetails.aspx?LotID=1435262&amp;a=384&amp;c=rbh">7</a></td>
  <td><a href="LotDetails.aspx?LotID=1435262&amp;a=384&amp;c=rbh">The Old Chapel, Station Road, Alvescot, OX18 2PU</a></td>
  <td>Unsold. The bidding reached £450,000. Contact the auctioneer.</td></tr>
 <tr class="lot-row"><td class="lotnum"><a href="LotDetails.aspx?LotID=1440801&amp;a=384&amp;c=rbh">17</a></td>
  <td><a href="LotDetails.aspx?LotID=1440801&amp;a=384&amp;c=rbh">1 Ashlar House, Reed Court, Swindon, SN3 4GA</a></td>
  <td>Sold post auction for an undisclosed amount.</td></tr>
 <tr class="lot-alt-row"><td class="lotnum"><a href="LotDetails.aspx?LotID=1440430&amp;a=384&amp;c=rbh">3</a></td>
  <td><a href="LotDetails.aspx?LotID=1440430&amp;a=384&amp;c=rbh">85 Millwright Way, Flitwick, MK45 1BQ</a></td>
  <td>Withdrawn Prior.</td></tr>
</table>
"""


def test_archive_preserves_event_denominators():
    events = rh.parse_archive(ARCHIVE)
    assert [(event["event_id"], event["auction_date"], event["lots_offered"]) for event in events] == [
        ("135951", "2026-10-14", 32),
        ("92155", "2024-12-04", 17),
    ]


def test_result_rows_preserve_addresses_outcomes_and_stable_event_identity():
    event = rh.parse_archive(ARCHIVE)[0]
    rows, malformed = rh.parse_result(RESULT, event, {"sha256": "abc"})
    assert malformed == [] and len(rows) == 4
    sold, unsold, sold_after, withdrawn = rows
    assert sold["appearance_id"] == "Robinson & Hall|robinson-hall:135951|eig-lot:1418663"
    assert sold["auction_date"] == "2026-10-14"
    assert sold["address"].startswith("Irthlingborough Town Band Club")
    assert sold["postcode"] == "NN9 5RG"
    assert sold["status"] == "sold" and sold["sale_price"] == 206000
    assert sold["sector"] == "commercial"
    assert unsold["status"] == "unsold" and unsold["sale_price"] is None
    assert unsold["reported_bid_reached"] == 450000
    assert sold_after["status"] == "sold_after" and sold_after["sale_price"] is None
    assert withdrawn["status"] == "withdrawn_prior"


def test_achieved_price_is_never_taken_from_an_unsold_bid():
    assert rh.status_and_price("Sold prior to auction for £120,000.") == ("sold_prior", 120000, None)
    assert rh.status_and_price("Sold post auction for an undisclosed amount.") == ("sold_after", None, None)
    assert rh.status_and_price("Unsold. The bidding reached £99,000.") == ("unsold", None, 99000)
    assert rh.status_and_price("Withdrawn Prior.") == ("withdrawn_prior", None, None)
