from source_reconciliation import reconcile


def test_collector_exclusions_are_not_invented_from_an_empty_publication_rejection_list():
    health={'source':'Bond Wolfe','status':'LIVE','reconciliation':{'source_lot_count':173,'lots_parsed':173,'commercial_mixed_candidates':25,'classification_rejections':148}}
    r=next(x for x in reconcile({'source_health':[health],'properties':[]})['sources'] if x['auctioneer']=='Bond Wolfe')
    assert r['residential_exclusions'] is None
    assert r['classification_rejections']==148
    assert r['publication_residential_exclusions']==0


def test_explicit_producer_residential_count_is_preserved_separately():
    h={'source':'Bond Wolfe','status':'LIVE','reconciliation':{'residential_exclusions':130}}
    r=next(x for x in reconcile({'source_health':[h],'properties':[]})['sources'] if x['auctioneer']=='Bond Wolfe')
    assert r['residential_exclusions']==130 and r['publication_residential_exclusions']==0


def test_tenant_brand_does_not_override_the_subject_retail_property():
    from property_summary import build_opportunity_summary
    title,_=build_opportunity_summary({'property_type':'Commercial investment','annual_rent':78800,
        'description':'The property comprises a ground floor shop with ancillary accommodation above. Tenant Profile: The retailer operates shops under The Food Warehouse brand.'})
    assert title=='RETAIL INVESTMENT'
