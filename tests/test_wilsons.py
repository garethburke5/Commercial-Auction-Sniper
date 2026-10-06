import json
from bs4 import BeautifulSoup
from collectors import wilsons as c

EVENT={'id':42,'day':'2099-10-21'}
URL=c.BASE+'/auctions/land-property-auction-scotland-42'

def row(**extra):
    return {'id':123,'lotNumber':7,'assetName':'10 High Street','status':'Awaiting Auction',
        'assetDetails':{'currency':'GBP','address':{'isoCountryCode':'GB','postcode':'AB1 2CD'},
            'description':'A freehold shop investment let to an established tenant. Guide Price £25,000–£50,000.',
            'featuredImageUrl':'https://example.org/official-hero.jpg','selling':{'price':25000,'qualifier':'guidePrice','tenure':{'type':'freehold'}}},**extra}

def test_primary_image_range_and_terminal_status():
    lot,outcome=c.parse_lot(row(withdrawn=True),EVENT,URL)
    assert outcome=='commercial' and lot.status=='WITHDRAWN'
    assert lot.auction_date=='2099-10-21' and lot.lot_number=='7'
    assert lot.guide_price==25000 and lot.guide_price_upper==50000
    assert lot.image_is_primary and lot.image_url.endswith('official-hero.jpg')

def test_republic_of_ireland_is_not_uk_inventory():
    r=row();r['assetDetails']['address']['isoCountryCode']='IE'
    assert c.parse_lot(r,EVENT,URL)==(None,'outside-uk')

def test_house_beside_hotel_and_converted_flat_are_residential():
    for text in ('A five bedroom detached property beside a hotel, accessed through the hotel car park.',
                 'A three bedroom residential conversion understood to have originally operated as commercial premises.'):
        r=row();r['assetDetails'].update(type=['house'],description=text)
        assert c.parse_lot(r,EVENT,URL)[1]=='residential'

def test_event_denominator_from_rendered_payload():
    payload='1:'+json.dumps({'auction':{'id':42,'startDate':'$D2099-10-21T11:00:00.000Z'},'totalCount':30})
    soup=BeautifulSoup('<script>self.__next_f.push('+json.dumps([1,payload])+')</script>','lxml')
    event=c.event_metadata(soup,'42')
    assert event['total']==30 and event['day']=='2099-10-21'

def test_truncated_public_lot_feed_is_degraded(monkeypatch):
    class Response:
        content=f'<a href="{URL.removeprefix(c.BASE)}">Current auction</a>'.encode()
    monkeypatch.setattr(c,'get',lambda u:Response())
    monkeypatch.setattr(c,'inspect_event',lambda u:({**EVENT,'total':2},[row()],['Catalogue denominator mismatch: 1/2 lots']))
    result=c.collect_wilsons()
    assert result.status=='DEGRADED' and not result.authoritative_snapshot
    assert result.reconciliation['advertised_current_lot_count']==2 and result.reconciliation['detail_pages_inspected']==1
    assert len(result.lots)==1

def test_legitimate_zero_preserves_complete_classification_evidence(monkeypatch):
    class Response:
        content=f'<a href="{URL.removeprefix(c.BASE)}">Current auction</a>'.encode()
    r=row();r['assetDetails']['description']='A two bedroom residential flat with a garden and vacant possession.'
    monkeypatch.setattr(c,'get',lambda u:Response())
    monkeypatch.setattr(c,'inspect_event',lambda u:({**EVENT,'total':1},[r],[]))
    result=c.collect_wilsons()
    assert result.status=='CATALOGUE PENDING' and result.authoritative_snapshot
    assert result.reconciliation['residential_exclusions']==result.reconciliation['detail_pages_inspected']==1
