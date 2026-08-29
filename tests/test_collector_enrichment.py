from collector_enrichment import extract_particulars, merge_enrichment


def test_auction_house_rich_lease_fields_and_clean_h1():
    html='''<html><main><h1>102-104 High Street, Redcar, Cleveland, TS10 3DL</h1>
    <div>Guide | £130,000</div><p>Retail investment let at £20,000 pa.</p>
    <p>Lease for a term of 12 years commencing 1 January 2025.</p>
    <p>Tenant break clause 1 January 2031. EPC Rating C (63).</p>
    <p>Rateable Value £18,500. Floor Area approximately 3,250 sq ft. FRI lease.</p></main></html>'''
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


def test_acuitus_scope_vat_epc_area_and_related_lot_contamination():
    html='''<html><main><h1>13 Stonehills, Welwyn Garden City, AL8 6ND</h1>
    <p>Freehold Former Bank Opportunity. Approx. 421.20 sq. m. (4,534 sq. ft.).</p>
    <p>Lot 26 Guide* Refer to Auctioneer</p><p>Tenure Freehold.</p>
    <p>VAT Not Elected for VAT</p><p>EPC Band E.</p>
    <h2>You may also be interested in</h2><p>Guide £850,000 EPC Band C.</p></main></html>'''
    f=extract_particulars(html,"Acuitus")
    assert f["guide"] is None
    assert f["guide_status"]=="Refer to Auctioneer"
    assert f["tenure"]=="Freehold"
    assert f["vat"]=="Not elected"
    assert f["epc"]=="E"
    assert abs(f["area_sqft"]-4534)<1
    assert abs(f["area_sqm"]-421.2)<0.1
    out=merge_enrichment({"guide":850000,"address":"13 Stonehills, Welwyn Garden City, AL8 6ND"},f)
    assert out["guide"] is None


def test_total_area_and_vat_applicable():
    html='''<main><h1>Former Wilko, 33-42 Fawcett Street, Sunderland, SR1 1RU</h1>
    <p>Total floor area of approximately 10,233.60 sq m (110,154 sq ft).</p>
    <p>VAT is applicable to this lot. EPC Band D. Tenure Freehold.</p></main>'''
    f=extract_particulars(html,"Acuitus")
    assert f["epc"]=="D"
    assert f["vat"]=="Applicable"
    assert abs(f["area_sqft"]-110154)<1
    assert abs(f["area_sqm"]-10233.6)<0.1


def test_service_charge_ground_rent_and_togc():
    html='''<main><h1>Unit 4 Example House, Leeds LS1 1AA</h1>
    <p>Leasehold. Service Charge £2,450 per annum. Ground Rent £250 pa.</p>
    <p>Sale is intended to be treated as a TOGC. EPC Rating B (42).</p></main>'''
    f=extract_particulars(html)
    assert f["service_charge"]==2450
    assert f["ground_rent"]==250
    assert f["togc"] is True
    assert f["epc"]=="B (42)"


def test_historical_rent_not_mistaken_for_current():
    html='''<main><h1>The Vaults, Manor Road, Chatham, ME4 6HW</h1>
    <p>Vacant. Previously let for £25,000 per annum. ERV £28,000 pa.</p></main>'''
    f=extract_particulars(html)
    assert f["rent"] is None
    assert f["erv"]==28000
