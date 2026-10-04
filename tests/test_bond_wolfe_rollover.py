from bs4 import BeautifulSoup
from unittest.mock import patch
from datetime import date
from collectors.bond_wolfe_v2 import collect, _sale_date, _inspect

URL='https://www.bondwolfe.com/auctions/properties/1-property-auction-example/'

def detail(date_text='22nd October 2099', kind='Commercial Investment', body='A ground floor shop let at £35,000 per annum.', extras=''):
    return BeautifulSoup(f'''<main><div class="PropertyHeader-description"><h1>1 High Street, Example, EX1 1AA</h1></div>
    <div class="PropertyHeader-price">Guide price £250,000+</div>
    <div class="Gallery-main"><ul class="Gallery-slider"><li><img src="/first.jpg"></li><li><img src="/second.jpg"></li></ul></div>
    <div class="PropertyDetail-description"><span class="PropertyDetail-attributes-types">{kind}</span>
    <div class="AuctionDetails-datetime">{date_text}</div><div class="Content"><h4>Property Description</h4>{body}</div></div>
    <form>Previously let at £99,999 per annum. Sold prior.</form>{extras}</main>''','lxml')

def test_date_comes_from_exact_sale_heading_not_viewing_lease_or_footer():
    s=detail(extras='<footer>Auction 10 September 2026</footer>')
    assert _sale_date(s)=='2099-10-22'
    assert _sale_date(BeautifulSoup('<h4>Auction: Thursday 5th February 2099</h4>','lxml'))=='2099-02-05'
    assert _sale_date(BeautifulSoup('<p>Lease dated 5 February 2099</p>','lxml')) is None

def test_scope_preserves_primary_current_income_and_ignores_related_lots():
    with patch('collectors.bond_wolfe_v2.soup',return_value=detail(extras='<div>Related properties Withdrawn £999,999</div>')):
        lot,out=_inspect((URL,'Lot 1 Commercial Investment','Lot 1',None),'2099-10-22')
    assert lot.guide_price==250000 and lot.annual_rent==35000
    assert lot.image_url.endswith('/first.jpg') and lot.image_is_primary
    assert lot.status=='CURRENT' and '99,999' not in lot.description
    assert out['outcome']=='commercial'

def test_rejects_wrong_sale_even_when_footer_has_current_auction():
    with patch('collectors.bond_wolfe_v2.soup',return_value=detail('10th September 2099',extras='<footer>Auction 22 October 2099</footer>')):
        lot,out=_inspect((URL,'Lot 1 Commercial','Lot 1',None),'2099-10-22')
    assert lot is None and out['outcome']=='other_sale'

def test_nearby_shops_do_not_turn_house_into_commercial():
    s=detail(kind='Residential Vacant',body='A three bedroom detached house. Location Nearby commercial premises and shop investments. Accommodation Three bedrooms.')
    with patch('collectors.bond_wolfe_v2.soup',return_value=s):
        lot,out=_inspect((URL,'Lot 1 Residential Vacant','Lot 1',None),'2099-10-22')
    assert lot is None and out['outcome']=='classification_rejected'

def test_traverses_unlabelled_terminal_and_residential_teasers_and_reconciles():
    order=BeautifulSoup(f'<main><h4>Auction: Thursday 22nd October 2099</h4><a href="{URL}">Lot 1 Withdrawn View lot</a><a href="{URL.replace("/1-","/2-")}">Lot 2 Residential Vacant View lot</a></main>','lxml')
    def fetch(url,**kw):
        if 'order-of-sale' in url:return order
        if '/2-' in url:return detail(kind='Residential Vacant',body='A two bedroom flat.')
        return detail()
    with patch('collectors.bond_wolfe_v2.soup',side_effect=fetch):r=collect()
    assert r.authoritative_snapshot and r.status=='LIVE'
    assert len(r.lots)==1 and r.lots[0].status=='WITHDRAWN'
    assert r.reconciliation['source_lot_count']==r.reconciliation['lots_parsed']==2
    assert r.reconciliation['classification_rejections']==1

def test_institutional_childrens_home_is_not_a_completed_residential_conversion():
    from collectors.publication_quality import commercial_decision
    institution={'description':"A former children's home. Accommodation: Fifteen bedrooms, communal facilities. Educational or community use subject to planning.", 'property_type':'Commercial vacant'}
    assert commercial_decision(institution) is True
    converted={**institution,'description':"A former children's home. Conversion works have been carried out into a residential dwelling, a private residence with five bedrooms."}
    assert commercial_decision(converted) is False

def test_residential_flat_above_shop_and_retirement_amenities_are_excluded():
    for body in ['A first floor duplex flat situated above a retail shop.', "A 1 bedroom retirement flat. Nearby restaurants and a communal restaurant."]:
        with patch('collectors.bond_wolfe_v2.soup',return_value=detail(kind='Residential Investment',body=body)):
            lot,out=_inspect((URL,'Lot 1 Residential Investment','Lot 1',None),'2099-10-22')
        assert lot is None and out['outcome']=='classification_rejected'


def test_demolished_commercial_use_is_not_current_commercial_stock():
    from collectors.publication_quality import commercial_decision
    assert commercial_decision({'address':'Former Public House site','description':'The site comprises residential development. The former public house has been demolished. Planning for 32 apartments.'}) is False
