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
