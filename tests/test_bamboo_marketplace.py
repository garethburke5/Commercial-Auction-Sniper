from scripts.harvest_bamboo_marketplace import normal_address, organisation_name


def test_organisation_display_is_canonical_attribution():
    item = {
        "organisation": "firminandco",
        "organisationDetails": {"name": "firminandco", "display": "Firmin & Co"},
        "branchDisplay": "Firmin & Co - Peterborough",
    }
    assert organisation_name(item) == "Firmin & Co"


def test_organisation_falls_back_without_inventing_branch_auctioneer():
    item = {"organisation": "example", "branchDisplay": "Example - Branch"}
    assert organisation_name(item) == "example"


def test_existing_trading_name_variant_uses_canonical_corpus_label():
    item = {"organisationDetails": {"display": "Clive Emson Auctioneers"}}
    assert organisation_name(item) == "Clive Emson"


def test_normal_address_collapses_source_formatting_only():
    assert normal_address("31 London Road, Bicester, OX26 6BU") == "31londonroadbicesterox266bu"
