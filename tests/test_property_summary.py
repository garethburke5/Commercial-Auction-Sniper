from property_summary import build_opportunity_summary


def test_st_helens_retail_investment_and_upper_floor_development():
    row = {
        "rent": 28500,
        "desc": (
            "A town centre investment and development opportunity comprising two adjoining ground floor retail units, "
            "both of which are let at a combined rental income of £28,500p/a along with vacant first and second floors. "
            "The upper floors are separately accessed and have previously been utilised as 9 bedsits with potential to "
            "develop into more suitable residential accommodation. 54 Bridge Street is let on a 15 year FRI lease. "
            "56-58 Bridge Street is let on a new 10 year FRI lease. We understand there are no break clauses."
        ),
        "fri": True,
    }
    title, facts = build_opportunity_summary(row)
    assert title == "RETAIL INVESTMENT + UPPER-FLOOR DEVELOPMENT"
    assert any("Two adjoining ground-floor retail units" in x for x in facts)
    assert any("9 bedsits" in x for x in facts)


def test_kettering_nominal_income_retail_surfaces_size_and_former_use():
    row = {
        "rent": None,
        "area_sqft": 8282,
        "desc": (
            "A freehold substantial retail premises with large frontage. The property is open plan and was formerly an Argos "
            "extending 8,282 sq ft benefitting from rear loading bay. We are advised there is a tenant in situ (KCU Charity) "
            "held on a one year term at Nill rent."
        ),
    }
    title, facts = build_opportunity_summary(row)
    assert title == "RETAIL OPPORTUNITY · NOMINAL INCOME"
    assert "Tenant in situ · nil rent" in facts
    assert "8,282 sq ft" in facts
    assert any("Former Argos" in x for x in facts)


def test_croydon_roofspace_is_development_not_ground_rent():
    row = {
        "property_type": "Commercial",
        "occupation": "Vacant",
        "desc": (
            "Freehold Residential Development Opportunity. Roof Space situated above a ground unit and five floors. "
            "Planning Permission Granted for Two Extra Storeys for Residential Development for 7 Flats. "
            "Roofspace offered with vacant possession. The rest of the property has been sold off on a long lease "
            "for 999 years to Brigante Properties Limited at a peppercorn ground rent."
        ),
    }
    title, _ = build_opportunity_summary(row)
    assert title == "CONSENTED ROOFTOP RESIDENTIAL DEVELOPMENT"


def test_genuine_ground_rent_investment_keeps_ground_rent_title():
    row = {
        "property_type": "Ground rent investment",
        "desc": "Freehold ground rent investment comprising 12 flats producing £3,600 per annum.",
        "rent": 3600,
    }
    title, _ = build_opportunity_summary(row)
    assert title == "GROUND RENT INVESTMENT"


def test_incidental_peppercorn_does_not_override_retail_development():
    row = {
        "property_type": "Retail",
        "desc": (
            "Retail and upper-floor development opportunity with vacant possession. "
            "An existing long lease reserves a peppercorn ground rent."
        ),
    }
    title, _ = build_opportunity_summary(row)
    assert title == "RETAIL + DEVELOPMENT OPPORTUNITY"

