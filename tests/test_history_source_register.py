from scripts.history_source_register import build,discover

def test_directory_deduplicates_exact_links_without_accepting_external_domains():
    s='<a href="/auctioneer/a">A</a><a href="/auctioneer/a">A</a><a href="https://evil.example/auctioneer/b">B</a><a href="/auctioneer/c">C</a>'
    assert [r['name'] for r in discover(s)]==['A','C']

def test_directory_names_are_not_claimed_as_integrations_or_complete():
    p={'by_auctioneer':{'A':50},'twenty_year_coverage':{'by_auctioneer_and_year':[{'auctioneer':'A','year':2020,'with_guide_price':20,'with_sale_price':30}]}}
    r=build(p,[{'name':'A'},{'name':'Unconnected branch'}],{}, {'runs':[{'source':'collector','outcome':'failed'}]}, [('gap.json',{'auctioneer':'A','lots_captured':7,'catalogue_complete':False,'errors':['count mismatch']})])
    assert r['directory_entries_not_linked']==1
    assert r['directory_entries'][0]['retained_appearances']==50
    assert not r['directory_entries'][0]['twenty_year_complete']
    assert r['latest_collector_attempts']['collector']['outcome']=='failed'
    assert r['unresolved_catalogues'][0]['lots_captured']==7
    assert not r['national_completeness_verified']
