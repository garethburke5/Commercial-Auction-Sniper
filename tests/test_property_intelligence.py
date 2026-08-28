from property_intelligence import extract_particulars,merge_enrichment

def test_extracts_core_investment_terms():
    text='''A ground floor retail unit let to Example Retail Ltd on a 12 year FRI lease from 1 January 2024 expiring 31 December 2035 at £20,000 per annum. Tenant break option on 31 December 2030. Rent review in January 2029. EPC rating C (62). Floor area 2,400 sq ft. Service charge £1,250 per annum.'''
    f=extract_particulars(text)
    assert f['rent']['value']==20000
    assert f['tenant']['value']=='Example Retail Ltd'
    assert f['lease_term_years']['value']==12
    assert '2035' in f['lease_expiry']['value']
    assert '2030' in f['break_clause']['value']
    assert f['repairing_basis']['value']=='FRI'
    assert f['epc']['value']=='C (62)'
    assert f['area_sqft']['value']==2400
    assert f['service_charge']['value']==1250

def test_does_not_use_historical_rent_as_passing_rent():
    text='Previously let at £34,000 per annum. ERV £25,000 per annum. The property is vacant.'
    f=extract_particulars(text)
    assert 'rent' not in f

def test_merge_does_not_overwrite_verified_existing_value():
    lot={'rent':21000,'tenant':'Verified Tenant'}
    x={'rent':{'value':20000,'source_text':'£20,000 pa','confidence':.9},'epc':{'value':'B (40)','source_text':'EPC B (40)','confidence':.9}}
    m=merge_enrichment(lot,x)
    assert m['rent']==21000
    assert m['tenant']=='Verified Tenant'
    assert m['epc']=='B (40)'
    assert 'rent' in m['particulars_evidence']
