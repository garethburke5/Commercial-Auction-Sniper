from scripts.audit_auction_coverage import audit


def test_healthy_collectors_without_catalogue_denominators_are_not_complete():
    snapshot={'properties':[], 'source_health':[{'source':'Example','status':'LIVE','lots_seen':50}],
              'excluded_properties':[{'publication_exclusion':'Pure residential: no commercial particulars'}]}
    result=audit(snapshot,{}, {'priority_assessments':[]})
    assert result['national_coverage_verified'] is False
    assert result['current']['sources_with_reconciled_denominators']==0
    assert result['current']['sources_without_reconciled_denominators']==1
    assert result['current']['all_sector_current_coverage_verified'] is False
    assert result['current']['retained_noncommercial_rows']==1


def test_reconciled_inventory_reports_missing_lots_without_calling_them_zero():
    snapshot={'properties':[], 'source_health':[{'source':'Example','status':'LIVE',
        'reconciliation':{'commercial_inventory_complete':True,
                          'source_commercial_urls':['https://example.test/lot/1']}}]}
    result=audit(snapshot,{}, {'priority_assessments':[]})
    assert result['current']['sources_with_reconciled_denominators']==1
    assert result['current']['unmatched_catalogue_lots']==1
    assert result['national_coverage_verified'] is False
