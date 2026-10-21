"""Relationship regression: source-backed Newbury plus unrelated holdout cases."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from web_platform.property_relationships import relationship, candidate_keys, result_evidence
from web_platform.market_context import MarketContext
from web_platform.history_access import preview, subject_key
from web_platform.tests.test_history_address_matching import archive
from web_platform.tests.test_platform import site

BASE={'address':'10 High Street, Example, AB1 2CD','tenure':'Freehold','auction_date':'2020-01-01','auctioneer':'Old Auctioneer','lot_number':'1','sector':'commercial','guide_price':200000,'annual_rent':10000,'original_url':'https://example.org/old'}

def test_newbury_real_sources_archive_refresh_and_separate_interests(tmp_path,site):
    fixture=json.loads((Path(__file__).parent/'fixtures/newbury_related_offerings.json').read_text())
    current,previous,old=fixture['current'],fixture['previous'],fixture['archive']
    market=archive(tmp_path,[old]);market.c.all_properties=[current,previous]
    result=market.for_property(current)
    assert result['history']==[] and result['comparables']==[]
    assert len(result['related_interests'])==1
    r=result['related_interests'][0]
    assert r['auction_date']=='2026-10-07' and r['result_evidence']['sale_price']==190000
    assert r['result_evidence']['kind']=='reported_sale'
    assert r['tenure']=='Freehold' and current['tenure']=='Leasehold'
    assert r['annual_rent']==26700 and current['annual_rent']==20000
    assert not r['price_comparable'] and not r.get('changes')
    assert subject_key(current)!=subject_key(previous)
    assert old['status']=='available' and old['sale_price'] is None
    public=site.env.get_template('history_preview.html').render(row=dict(current,id='newbury'),history_preview=preview(result))
    assert 'Related property interests found' in public and 'like-for-like' in public
    for secret in ('190,000','26,700',previous['url']):assert secret not in public
    private=site.env.get_template('history_private.html').render(row=current,history=[],market=result,kind='private-history')
    for fact in ('£190,000','£26,700','£20,000','1 The Arcade','151A','Reported sold','7 October 2026'):assert fact in private
    assert 'Guide changed' not in private and 'Rent changed' not in private
    assert previous['url'] in private

@pytest.mark.parametrize('changes',[
    {'address':'Unit 2, 10 High Street, Example, AB1 2CD'},
    {'address':'10 High Street, First Floor, Example, AB1 2CD'},
    {'address':'10-12 High Street, Example, AB1 2CD'},
    {'address':'10 High Street and 1 The Arcade, Example, AB1 2CD'},
    {'tenure':'Leasehold'},
    {'area_sqft':500},
    {'title_numbers':['AB123456','AB654321']},
])
def test_unit_disposals_subdivision_interests_and_titles_never_exact(tmp_path,changes):
    old=dict(BASE,area_sqft=1000,title_numbers=['AB123456'])
    current=dict(old,auction_date='2026-11-03',url='https://different-auctioneer.test/lot',original_url=None,**changes)
    result=archive(tmp_path,[old]).for_property(current)
    assert result['history']==[] and len(result['related_interests'])==1
    assert not result['related_interests'][0]['price_comparable']
    assert result['comparables']==[]

@pytest.mark.parametrize('address',[
    '11 High Street, Example, AB1 2CD','10A High Street, Example, AB1 2CD',
    '10 High Road, Example, AB1 2CD','10 High Street, Example, AB1 2CE',
    '110 High Street, Example, AB1 2CD','1 High Street, Example, AB1 2CD',
])
def test_neighbours_different_streets_postcodes_and_numeric_collisions_do_not_link(address):
    assert relationship(BASE,dict(BASE,address=address)) is None


def test_cross_auctioneer_alias_is_exact_and_missing_tenure_not_confirmed(tmp_path):
    current=dict(BASE,address='10 High St., County, AB1 2CD',source='Another auctioneer',auction_date='2026-11-03',url='https://new.test/lot',original_url=None)
    context=archive(tmp_path,[BASE]).for_property(current)
    assert len(context['history'])==1 and not context['related_interests']
    assert context['history'][0]['price_comparable']
    assert relationship(BASE,dict(BASE,tenure=None),same_address=True)['price_comparable'] is False


def test_shared_title_connects_readdressed_unit_but_not_other_postcode():
    old=dict(BASE,title_numbers=['AB123456'])
    current=dict(BASE,address='Shop 3, Arcade House, Example, AB1 2CD',tenure='Leasehold',title_number='AB123456')
    assert relationship(old,current)['match_type']=='related_interest'
    assert relationship(old,dict(current,address='Shop 3, Arcade House, Example, AB1 2CE')) is None

@pytest.mark.parametrize('status,label,price',[
    ('sold','Reported sold',190000),('sold_prior','Reported sold before auction',190000),
    ('unsold','Unsold',None),('withdrawn','Withdrawn',None),
    ('available','Available — no sale recorded',None),('unknown','Outcome not verified',None),
])
def test_result_labels_do_not_promote_missing_or_unsold_to_sales(status,label,price):
    result=result_evidence({'status':status,'sale_price':190000})
    assert result['label']==label and result['sale_price']==price


def test_different_interests_never_get_guide_or_rent_change_arrows(tmp_path):
    past=[dict(BASE,auction_date='2020-01-01',tenure='Freehold',area_sqft=2000),
          dict(BASE,auction_date='2021-01-01',tenure='Leasehold',area_sqft=1000,guide_price=100000)]
    result=archive(tmp_path,past).for_property(dict(BASE,auction_date='2026-01-01',tenure='Leasehold',area_sqft=1000))
    assert len(result['history'])==len(result['related_interests'])==1
    assert not any(r.get('changes') for r in result['history']+result['related_interests'])


def test_new_long_lease_and_changed_schedule_prevent_price_comparison():
    old=dict(BASE,tenure='Leasehold',description='Held on a 99 year lease')
    now=dict(old,description='New 999 year lease at a peppercorn')
    assert not relationship(old,now,same_address=True)['price_comparable']
    old=dict(BASE,tenancy_schedule=[{'Address':'10 High Street'},{'Address':'1 The Arcade'}])
    now=dict(BASE,tenancy_schedule=[{'Address':'10 High Street'}])
    assert relationship(old,now,same_address=True)['match_type']=='related_interest'


def test_range_interiors_are_not_assumed_to_be_part_of_the_asset():
    assert relationship(dict(BASE,address='10-14 High Street, AB1 2CD'),dict(BASE,address='11 High Street, AB1 2CD')) is None


def test_other_actual_catalogue_unit_disposals_remain_separate(tmp_path):
    cases=json.loads((Path(__file__).parent/'fixtures/related_interest_holdouts.json').read_text())
    for i,case in enumerate(cases):
        directory=tmp_path/str(i);directory.mkdir()
        result=archive(directory,[case['previous']]).for_property(case['current'])
        assert result['history']==[] and len(result['related_interests'])==1
        assert not result['related_interests'][0]['price_comparable']
        assert result['related_interests'][0]['original_url']==case['previous']['original_url']


@pytest.mark.parametrize('changed',[{'tenure':'Leasehold'},{'area_sqft':500},{'unit_count':1},{'title_numbers':['AB654321']}])
def test_observation_price_changes_suppressed_when_interest_or_extent_changes(changed):
    from web_platform.market_context import address_key
    row=dict(BASE,tenure='Freehold',area_sqft=1000,unit_count=2,title_numbers=['AB123456'])
    previous=dict(row,observed_at='2026-01-01',guide_price=200000)
    current=dict(previous,observed_at='2026-02-01',guide_price=100000,**changed)
    m=MarketContext(None);m.loaded=True
    m.observed[address_key(row['address'])]=[{'tenure':'Freehold','address_as_published':row['address'],'source_evidence':{'listing_url':'https://source.test/1'},'observations':[previous,current]}]
    assert m.observations(dict(row,**changed))==[]
