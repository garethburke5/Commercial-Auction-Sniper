from scripts.harvest_butters_john_bee_archive import (
    catalogue_enrichment,
    catalogue_lot_pages,
    exact_date,
    parse_archive,
    status_and_price,
)


ARCHIVE = """
<h4>14th September</h4>
<p><a href="https://files.example/sep-catalogue.pdf">View Catalogue</a></p>
<p><a href="https://files.example/sep-results.pdf">Results</a></p>
<h4>13th July 2026</h4>
<p><a href="/july-catalogue.pdf">View Catalogue</a></p>
<p><a href="/july-results.pdf">Results</a></p>
"""


CATALOGUE_TEXT = """
Property Monday 14th September, 2026 auction catalogue
\f
       LOT                     *Guide price

   01                          £46,000 plus

36 Lonsdale Street, Stoke-on-Trent, Staffordshire, ST4 4DP
• Retail shop with flat above                         Legal Representative
• Freehold
• Shop is currently let at £800 pcm
\f
11
  LOT                          *Guide price

                               £20,000

Flat 317, 56 Hounds Gate, Nottingham, NG1 6BH
• Student accommodation
• Leasehold
• Currently tenanted at £5,332 p/a
"""


def test_archive_requires_ordered_catalogue_result_pairs():
    events = parse_archive(ARCHIVE, "https://buttersjohnbee.com/auction-catalogues")
    assert len(events) == 2
    assert events[0]["archive_date_text"] == "14th September"
    assert events[0]["catalogue_url"] == "https://files.example/sep-catalogue.pdf"
    assert events[1]["result_url"] == "https://buttersjohnbee.com/july-results.pdf"


def test_catalogue_date_is_exact_even_when_archive_heading_omits_year():
    assert exact_date(CATALOGUE_TEXT.split("\f", 1)[0]) == "2026-09-14"
    assert exact_date("13th July 2026") == "2026-07-13"


def test_catalogue_lot_pages_handles_numbers_before_or_after_lot_heading():
    pages = catalogue_lot_pages(CATALOGUE_TEXT)
    assert sorted(pages) == ["1", "11"]
    assert pages["1"][0]["page_number"] == 2
    assert pages["11"][0]["page_number"] == 3


def test_catalogue_enrichment_preserves_type_tenure_and_monthly_rent():
    pages = catalogue_lot_pages(CATALOGUE_TEXT)
    enriched, mismatch = catalogue_enrichment(
        pages["1"],
        "36 Lonsdale Street, Stoke-on-Trent, Staffordshire, ST4 4DP",
    )
    assert mismatch is None
    assert enriched["property_type"] == "Retail shop with flat above"
    assert enriched["tenure"] == "Freehold"
    assert enriched["annual_rent"] == 9600
    assert enriched["catalogue_page_numbers"] == [2]


def test_catalogue_enrichment_keeps_annual_rent_distinct_from_guide():
    pages = catalogue_lot_pages(CATALOGUE_TEXT)
    enriched, mismatch = catalogue_enrichment(
        pages["11"],
        "Flat 317, 56 Hounds Gate, Nottingham, NG1 6BH",
    )
    assert mismatch is None
    assert enriched["annual_rent"] == 5332
    assert enriched["property_type"] == "Student accommodation"


def test_published_outcomes_and_prices_remain_distinct():
    assert status_and_price("£61,500") == ("sold", 61500)
    assert status_and_price("Sold Prior") == ("sold_prior", None)
    assert status_and_price("Sold Post") == ("sold_after", None)
    assert status_and_price("Unsold") == ("unsold", None)
    assert status_and_price("Postponed") == ("postponed", None)
    assert status_and_price("Withdrawn") == ("withdrawn", None)
