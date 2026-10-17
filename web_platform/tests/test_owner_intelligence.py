"""Owner intelligence must be title-evidenced, postcode-specific and non-speculative."""
import json

from web_platform.owner_intelligence import OwnerRegistry


def row(address, path="/property/example/", date="2026-10-21", guide=180000):
    return {
        "address": address, "path": path,
        "auction_date": date, "guide_price": guide,
    }


def test_identifies_two_genuine_goldfinger_holdings_and_crosslinks():
    registry = OwnerRegistry.from_file()
    liverpool = row("22 Broadway, Norris Green, Liverpool L11 1BZ", "/property/liverpool/")
    wimbledon = row("114 Haydons Road, South Wimbledon, London SW19 1AW", "/property/wimbledon/", guide=150000)
    by_title = registry.index([liverpool, wimbledon])
    info = registry.context(liverpool, by_title)
    assert info["company_number"] == "07198257"
    assert info["title_number"] == "MS38328"
    assert info["recorded_purchase_price"] == 350000
    assert info["related"][0]["path"] == "/property/wimbledon/"
    assert info["related"][0]["title_number"] == "SY260679"
    assert "not established" in info["seller_status"]
    assert "hypotheses" in info["motivation_status"]
    reverse = registry.context(wimbledon, by_title)
    assert reverse["recorded_purchase_price"] == 242000
    assert reverse["related"][0]["path"] == "/property/liverpool/"


def test_does_not_claim_unverified_owner_based_on_name_or_proximity():
    registry = OwnerRegistry.from_file()
    for address in (
        "122 Broadway, Liverpool L11 1BZ",
        "22 Broadway, Liverpool L12 1BZ",
        "114 Haydons Road, London SW19 1AX",
        "114 Haydons Road, Sutton SM1 1AA",
        "22 Broadway, London SW19 1AW",
        "",
    ):
        assert registry.context(row(address)) is None


def test_optional_the_in_street_works_but_no_broad_match():
    registry = OwnerRegistry.from_file()
    assert registry.context(row("22 The Broadway, Norris Green, Liverpool L11 1BZ"))["title_number"] == "MS38328"


def test_ambiguous_title_evidence_fails_closed():
    registry = OwnerRegistry.from_file()
    sample = registry.records[0].copy()
    other = dict(sample, title_number="UNCONFIRMED")
    registry = OwnerRegistry([sample, other])
    assert registry.match(row("22 Broadway, Liverpool L11 1BZ")) is None


def test_no_link_invented_when_second_lot_not_in_catalogue():
    registry = OwnerRegistry.from_file()
    liverpool = row("22 Broadway, Liverpool L11 1BZ")
    info = registry.context(liverpool, registry.index([liverpool]))
    assert info["related"][0]["path"] is None


def test_fixture_contains_only_confirmed_registered_title_relations():
    registry = OwnerRegistry.from_file()
    assert all(item["evidence"].startswith("HM Land Registry official freehold title") for item in registry.records)
    assert all(item["verified_as_of"] == "2026-10-14" for item in registry.records)
    assert all("seller" not in item for item in registry.records)
    assert len(registry.records) == 2


def test_rendered_property_page_contains_sourced_owner_block(tmp_path):
    from web_platform.catalogue import Catalogue
    from web_platform.site import Site
    (tmp_path / "data/auction_history").mkdir(parents=True)
    properties = [
        {"source": "Savills Auctions", "url": "https://example.com/lot/283",
         "address": "22 Broadway, Liverpool L11 1BZ", "lot_number": "283",
         "auction_date": "2026-10-21", "description": "Retail investment subject to an occupational lease. " * 15,
         "annual_rent": 25000, "guide_price": 180000, "tenure": "Freehold", "property_type": "Retail"},
        {"source": "Savills Auctions", "url": "https://example.com/lot/278",
         "address": "114 Haydons Road, London SW19 1AW", "lot_number": "278",
         "auction_date": "2026-10-21", "description": "Ground floor retail lease. " * 20,
         "annual_rent": 15000, "guide_price": 150000, "tenure": "Freehold", "property_type": "Retail"},
    ]
    (tmp_path / "data/properties.json").write_text(json.dumps({"properties": properties, "generated_at": "2026-10-17"}))
    (tmp_path / "data/auction_history/progress.json").write_text(json.dumps({"individual_lot_records_captured": 2}))
    site = Site(Catalogue(tmp_path), "https://example.org")
    pages = dict(site.routes())
    liverpool = next(item for item in site.catalogue.all_properties if "Liverpool" in item["address"])
    wimbledon = next(item for item in site.catalogue.all_properties if "London" in item["address"])
    html = pages[liverpool["path"]]
    assert 'id="owner-intelligence"' in html
    assert "Goldfinger Commercial Limited" in html
    assert "MS38328" in html
    assert "not a current valuation" in html
    assert wimbledon["path"] in html
    assert "Sale motivation not independently established" in html
    assert "a forced sale" in html
