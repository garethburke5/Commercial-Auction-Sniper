from scripts.harvest_sdl_legacy_catalogues import (
    discover_catalogues, parse_catalogue_cards, parse_catalogue_identity,
)


ARCHIVE = """
<html><body>
<a href="/catalogues/archive/">Archive</a>
<a href="/catalogues/may-2022/">May 2022</a>
<a href="/catalogues/january-2024-national-property-auction-catalogue/">January 2024</a>
<a href="/catalogues/december-2025/">December 2025</a>
<a href="/catalogues/january-2026/">January 2026</a>
</body></html>
"""


CATALOGUE = """
<html><body>
<h1>National Property Auction</h1>
<p>Thursday 31st January 2024 at 9:00am</p>
<a href="/auction/1237/national-property-auction-2024-01-31/">View all lots</a>
<section class="featured">
  <article>
    <p>Lot 100</p>
    <ul><li>Apartment 216, 15 Hatton Garden, Liverpool L3 2HA</li>
        <li>Guide price* £70,000+ (plus fees)</li></ul>
    <a href="/property/49099/apartment-for-auction-liverpool/">View more</a>
    <img src="/media/49099.jpg">
  </article>
  <article>
    <p>Lot 2A</p>
    <ul><li>Gospel Hall, Caledonian Road, Milton Keynes MK13 0AP</li>
        <li>Guide Price £25,000 - £30,000</li></ul>
    <a href="/property/48861/place-of-worship-for-auction-milton-keynes/">View more</a>
  </article>
</section>
</body></html>
"""


def test_archive_selects_only_pre_btg_retained_catalogues():
    found = discover_catalogues(ARCHIVE)
    assert [item["month_hint"] for item in found] == ["2022-05", "2024-01"]
    assert found[0]["url"] == "https://www.sdlauctions.co.uk/catalogues/may-2022/"


def test_catalogue_requires_one_exact_auction_identity():
    auction_id, auction_date = parse_catalogue_identity(
        CATALOGUE, "https://www.sdlauctions.co.uk/catalogues/january-2024/"
    )
    assert auction_id == "1237"
    assert auction_date == "2024-01-31"


def test_featured_cards_become_strict_address_appearances():
    rows = parse_catalogue_cards(
        CATALOGUE,
        "https://www.sdlauctions.co.uk/catalogues/january-2024/",
        "1237", "2024-01-31", {"sha256": "catalogue"},
    )
    assert len(rows) == 2
    by_id = {row["property_id"]: row for row in rows}
    apartment = by_id["49099"]
    assert apartment["appearance_id"] == "SDL Property Auctions|auction:1237|property:49099"
    assert apartment["lot_number"] == "100"
    assert apartment["address"] == "Apartment 216, 15 Hatton Garden, Liverpool L3 2HA"
    assert apartment["postcode"] == "L3 2HA"
    assert apartment["guide_price"] == 70000
    assert apartment["record_quality"] == "address_record"
    hall = by_id["48861"]
    assert hall["lot_number"] == "2A"
    assert hall["guide_price"] == 25000
    assert hall["guide_price_high"] == 30000
    assert hall["sector"] in {"commercial", "unknown"}


def test_cards_without_stable_property_identity_are_not_admitted():
    html = CATALOGUE.replace(
        '/property/49099/apartment-for-auction-liverpool/',
        '/news/not-a-property/',
    ).replace(
        '/property/48861/place-of-worship-for-auction-milton-keynes/',
        '/search/',
    )
    try:
        parse_catalogue_cards(
            html, "https://www.sdlauctions.co.uk/catalogues/january-2024/",
            "1237", "2024-01-31", {},
        )
    except ValueError as exc:
        assert "no fully evidenced" in str(exc)
    else:
        raise AssertionError("identity-free catalogue cards were admitted")
