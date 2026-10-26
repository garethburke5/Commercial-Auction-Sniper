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

LEGACY_JUNE = """
<table>
 <tr><th>Lot</th><th>Address</th><th>Result</th></tr>
 <tr><td><a href="https://auctioneertemplates.eigroup.co.uk/LotDetails.aspx?LotID=1046743&amp;a=384&amp;c=rbh">1</a></td>
  <td><a href="https://auctioneertemplates.eigroup.co.uk/LotDetails.aspx?LotID=1046743&amp;a=384&amp;c=rbh">32 Wilson Crescent, Irthlingborough, NN9 5PP</a></td>
  <td>Sold for £168,000</td></tr>
 <tr><td><a href="https://auctioneertemplates.eigroup.co.uk/LotDetails.aspx?LotID=1046750&amp;a=384&amp;c=rbh">7</a></td>
  <td><a href="https://auctioneertemplates.eigroup.co.uk/LotDetails.aspx?LotID=1046750&amp;a=384&amp;c=rbh">Land R/O 22 &amp; 22A Western Avenue, Buckingham, MK18 1LN</a></td>
  <td>Sold prior to auction, for an undisclosed amount</td></tr>
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


def test_legacy_linked_article_preserves_exact_date_and_stable_eig_ids():
    rows, malformed = rh.parse_legacy_june_article(LEGACY_JUNE, {"sha256": "article"})
    assert malformed == [] and len(rows) == 2
    assert rows[0]["appearance_id"] == (
        "Robinson & Hall|robinson-hall:wordpress-2021-06-17|legacy-lot:1046743"
    )
    assert rows[0]["auction_date"] == "2021-06-17"
    assert rows[0]["sale_price"] == 168000
    assert rows[1]["status"] == "sold_prior" and rows[1]["sale_price"] is None


def test_april_image_transcription_keeps_month_only_evidence_undated():
    rows = rh.april_image_rows({"sha256": "article"}, {"sha256": "image"})
    assert len(rows) == 17
    assert len({row["lot_number"] for row in rows}) == 17
    assert all(row["auction_date"] is None for row in rows)
    assert all(row["source_month"] == "2021-04" for row in rows)
    assert sum(row["sale_price"] is not None for row in rows) == 14
    assert sum(row["sector"] == "land" for row in rows) == 6
    water_tower = rows[6]
    assert water_tower["status"] == "unsold"
    assert water_tower["sale_price"] is None
    assert water_tower["reported_bid_reached"] == 159000


def test_april_duplicate_fingerprint_requires_address_result_and_price():
    row = rh.april_image_rows({"sha256": "article"}, {"sha256": "image"})[0]
    key = (rh.address_key(row["address"]), row["status"], row["sale_price"])
    assert key == (
        "landatrookeryhousethelanewybostonbedfordbedfordshiremk443ap",
        "sold",
        80000,
    )


def test_2023_image_transcriptions_keep_exact_catalogue_dates_and_prices():
    schedule = {"sha256": "schedule"}
    june = rh.dated_image_rows(
        rh.JUNE_2023_ROWS, rh.LEGACY_JUNE_2023_DATE,
        rh.LEGACY_JUNE_2023_ARTICLE_URL, "2023-06-28",
        {"sha256": "article"}, {"sha256": "image"}, schedule,
    )
    august = rh.dated_image_rows(
        rh.AUGUST_2023_ROWS, rh.LEGACY_AUGUST_2023_DATE,
        rh.LEGACY_AUGUST_2023_ARTICLE_URL, "2023-08-23",
        {"sha256": "article"}, {"sha256": "image"}, schedule,
    )
    assert len(june) == 19 and len(august) == 24
    assert {row["auction_date"] for row in june} == {"2023-06-15"}
    assert {row["auction_date"] for row in august} == {"2023-08-03"}
    assert sum(row["sale_price"] is not None for row in june) == 15
    assert sum(row["sale_price"] is not None for row in august) == 16
    assert sum(row["status"] == "withdrawn_prior" for row in june) == 2
    assert sum(row["status"] == "unsold" for row in august) == 4
    assert all(row["auction_date_source_evidence"] == schedule for row in june + august)
    assert august[3]["reported_bid_reached"] == 120000
    assert august[3]["sale_price"] is None
