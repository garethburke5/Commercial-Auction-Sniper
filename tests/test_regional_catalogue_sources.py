import json
import pytest
from bs4 import BeautifulSoup
from collectors import gth,agents_property as apa
from collectors.publication_quality import lot_identity


def page(s):return BeautifulSoup(s,'lxml')

def gth_page(text,identity=1,day='2026-11-10',**extra):
    data={'propertyId':identity,'displayAddress':'Business Park, Taunton, TA1','description':text,'auctionDate':day,'price':'Guide Price £250,000','status':'Sold STC','photos':[],**extra}
    return page('<script>Homeflow.set("property_data",'+json.dumps(data)+');</script>')


def test_gth_keeps_units_separate_and_does_not_invent_achieved_prices():
    a=gth.detail('https://www.gth.net/properties/1',{'property_id':1},gth_page('Newly built industrial premises. Unit 06 provides storage accommodation.',exchangedPrice=280000))
    b=gth.detail('https://www.gth.net/properties/2',{'property_id':2},gth_page('Newly built industrial premises. Unit 16-25 provides storage accommodation.',identity=2))
    assert a.address.startswith('Unit 06,') and b.address.startswith('Unit 16-25,')
    assert lot_identity(a.to_dict())!=lot_identity(b.to_dict())
    assert a.guide_price==250000 and a.sale_price is None and a.status=='UNDER OFFER'
    assert gth.classification(a.to_dict()) is True


def test_gth_rejects_venue_and_neighbourhood_classification():
    for text in ['Productive agricultural land. For Sale by Public Auction at the Batch Country Hotel.',
                 'A pasture field on the fringes of the village of Walton . For Sale by Public Auction at The Shrubbery Hotel.',
                 'A detached house with a garden. The village has a public house and supermarket.']:
        assert gth.classification({'description':text}) is not True
    assert gth.classification({'description':'Prominent business premises comprising ground floor shop with first floor offices.'}) is True


def test_gth_quarantines_identity_date_and_pagination_conflicts():
    with pytest.raises(ValueError,match='ID'):gth.detail('u',{'property_id':2},gth_page('Industrial premises.'))
    with pytest.raises(ValueError,match='Conflicting'):gth.detail('u',{'property_id':1},gth_page('Industrial premises. Public auction on 11 November 2026.'))
    with pytest.raises(ValueError,match='exact'):gth.detail('u',{'property_id':1},gth_page('Industrial premises.',day=None))
    # A server that silently ignores page-N cannot certify complete inventory.
    data={'properties':[{'property_id':1,'property_url':'/properties/1'}], 'pagination':{'current_page':1,'total_count':2,'has_next_page':True}}
    result=gth.collect(fetcher=lambda u:page('<script>var propertyData = '+json.dumps(data)+'</script>'))
    assert result.status=='DEGRADED' and not result.lots
    assert 'different page' in result.message


def test_agents_load_more_preserves_anonymous_search_session(monkeypatch):
    def listing(n):
        return f'<article class="card--property"><a href="/property/{n}/">Shop</a><span class="card-price">£100,000 (Guide Price)</span></article>'+ (f'<a class="ur-load-more-link" data-current="{n}" data-max="2" data-found-posts="2" data-page-type="page"></a>' if n==1 else '')
    class Response:
        def __init__(self,s):self.content=s.encode()
        def raise_for_status(self):pass
    class Session:
        opened=False
        def get(self,u,**kw):self.opened=True;return Response(listing(1))
        def post(self,u,**kw):
            assert self.opened and kw['data']=={'action':'ur_load_more','page_number':2,'page_type':'page'}
            return Response(listing(2))
    monkeypatch.setattr(apa.requests,'Session',Session)
    monkeypatch.setattr(apa,'fetch',lambda u:page('<h1 class="single-property-title">Commercial</h1><p>'+u.split('/')[-2]+' High Street, AB1 2CD</p><div id="property_info">Freehold shop investment. For sale by auction. Annual rent £12,000 per annum.</div>'))
    result=apa.collect()
    assert len(result.lots)==2 and result.reconciliation['catalogue_complete']
    assert result.reconciliation['unknown_auction_date_lots']==2
    assert result.reconciliation['past_auction_exclusions']==0
    assert all(l.auction_date is None and l.guide_price==100000 for l in result.lots)


def test_agents_does_not_classify_house_from_agent_marketing_or_nearby_shops():
    assert apa.classification({'description':'SOLD PRIOR Two bedroom bungalow. Example Estate Agents are delighted to offer this residential property.'}) is False
    assert apa.classification({'description':'Three bedroom detached family home. The village has a public house.', 'property_type':'House'}) is False
    assert apa.classification({'description':'A site in an established business park. The site benefits from outline planning permission for the development of B2 (General Industrial) and B8 (Storage) accommodation.'}) is True


def test_gth_wider_estate_extent_is_not_assigned_to_unit():
    lot=gth.detail('u',{'property_id':1},gth_page('Newly built industrial premises. Unit 13 provides storage accommodation. Example Park comprises a mixed-use business park in excess of 40 acres. Already on the established business park are amenities such as a hotel and restaurant.'))
    row=lot.to_dict()
    assert row['site_area_acres'] is None and row['property_type']=='Industrial / Warehouse'
