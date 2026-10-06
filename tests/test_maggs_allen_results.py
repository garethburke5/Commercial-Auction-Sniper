from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_maggs_allen_results as maggs


INDEX = """
<div class="card">
  <div class="auction-property-image" style="background:url(/resize/33061135/0/600) no-repeat center"></div>
  <div class="card-title">
    <h2><a href="/property-details/33061135/bristol-city/bristol/st-nicholas-road-1">
      St. Nicholas Road, St. Pauls,<br>Bristol, BS2 9JJ
    </a></h2>
    <h2 class="black"><a href="/property-details/33061135/bristol-city/bristol/st-nicholas-road-1">
      Sold at Auction for £341,000
    </a></h2>
  </div>
  <ul>
    <li>Guide Price £275,000</li><li>April 2024 Auction</li>
    <li>Well-presented mid-terraced period house</li><li>Two double bedrooms</li>
  </ul>
</div>
<div class="card">
  <div class="card-title">
    <h2><a href="/property-details/32232994/south-gloucestershire/bristol/gloucester-road-3">
      209-211 Gloucester Road, Patchway, Bristol, BS34 6ND
    </a></h2>
    <h2 class="black">Sold at Auction for £1,150,000</h2>
  </div>
  <ul><li>Guide Price £950,000</li><li>Commercial investment</li></ul>
</div>
"""

DETAIL = """
<script type="application/ld+json">
{"@context":"https://schema.org/","@type":"Residence","description":"FOR SALE BY AUCTION - This property is due to feature in our online auction on 25 April 2024 at 6.00pm. SUMMARY - SOLD FOR £341,000."}
</script>
"""


def test_index_preserves_stable_ids_prices_and_address_rows():
    rows = maggs.parse_index(INDEX, {"source_url": maggs.RESULTS_URL})
    assert len(rows) == 2
    assert rows[0]["source_property_id"] == "33061135"
    assert rows[0]["address"] == "St. Nicholas Road, St. Pauls, Bristol, BS2 9JJ"
    assert rows[0]["postcode"] == "BS2 9JJ"
    assert rows[0]["guide_price"] == 275000
    assert rows[0]["sale_price"] == 341000
    assert rows[0]["published_auction_month"] == "April 2024"
    assert rows[1]["sale_price"] == 1150000
    assert rows[1]["published_auction_month"] is None


def test_detail_narrative_supplies_exact_date_without_month_inference():
    detail = maggs.parse_detail(DETAIL)
    assert detail["auction_date"] == "2024-04-25"
    assert detail["source_schema_type"] == "Residence"
    assert "online auction on 25 April 2024" in detail["detail_description"]


def test_date_parser_handles_weekday_and_ordinal_but_not_month_only():
    assert maggs.parse_exact_date("Auction to be held on Thursday, 21st July 2022 at 18:00") == "2022-07-21"
    assert maggs.parse_exact_date("April 2024 Auction") is None


def test_conflicting_detail_year_is_not_promoted_to_exact_date():
    assert maggs.reconcile_exact_date("2024-04-25", "April 2025") == (
        None,
        "detail narrative date 2024-04-25 conflicts with retained index month April 2025",
    )
    assert maggs.reconcile_exact_date("2024-04-25", "April 2024") == ("2024-04-25", None)
