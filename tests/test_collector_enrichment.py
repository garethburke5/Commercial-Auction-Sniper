from collector_enrichment import extract_particulars, merge_enrichment

def test_auction_house_rich_lease_fields_and_clean_h1():
    html='''<html><main><h1>102-104 High Street, Redcar, Cleveland, TS10 3DL</h1>
    <div>Guide | £130,000</div><p>Retail investment let at £20,000 pa.</p>
    <p>Lease for a term of 12 years commencing 1 January 2025.</p>
    <p>Tenant break clause 1 January 2031. EPC Rating C (63).</p>
    <p>Rateable Value £18,500. Floor Area 3,250 sq ft. FRI lease.</p></main></html>'''
    f=extract_particulars(html,"Auction House London")
    assert f["address"]=="102-104 High Street, Redcar, Cleveland, TS10 3DL"
    assert f["guide"]==130000
    assert f["rent"]==20000
    assert f["lease_term"]=="12 years"
    assert "2031" in f["break_clause"]
    assert f["epc"]=="C (63)"
    assert f["rateable_value"]==18500
    assert f["area_sqft"]==3250
    assert f["fri"] is True

def test_bond_wolfe_financial_and_tenancy_fields():
    html='''<html><main><h1>33-35 Cape Hill, Smethwick, B66 4RX</h1>
    <p>Guide Price £175,000</p><p>Current rental income £19,800 per annum.</p>
    <p>Tenant: Example Retail Limited. Lease for 10 years from 24 June 2024.</p>
    <p>Rent review 24 June 2029. EPC B (45). Freehold.</p></main></html>'''
    f=extract_particulars(html,"Bond Wolfe")
    assert f["guide"]==175000
    assert f["rent"]==19800
    assert f["tenant"]=="Example Retail Limited"
    assert f["lease_term"]=="10 years"
    assert f["tenure"]=="Freehold"
    assert f["epc"]=="B (45)"

def test_contaminated_regional_title_is_repaired_from_exact_h1():
    row={"address":"For Sale By Auction | 14:00, 24 September 2026 Unit 7 Garioch Shopping Centre, Inverurie AB51 4SR"}
    facts={"address":"Unit 7 Garioch Shopping Centre, Inverurie AB51 4SR","guide":100000}
    out=merge_enrichment(row,facts)
    assert out["address"]==facts["address"]
    assert out["guide"]==100000

def test_historical_rent_not_mistaken_for_current():
    html='''<main><h1>The Vaults, Manor Road, Chatham, ME4 6HW</h1>
    <p>Vacant. Previously let for £25,000 per annum. ERV £28,000 pa.</p></main>'''
    f=extract_particulars(html)
    assert f["rent"] is None
    assert f["erv"]==28000
