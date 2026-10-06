from bs4 import BeautifulSoup
from collectors import iamsold as c

URL='https://www.iamsold.co.uk/property/'+'a'*32+'/'

def page(text): return BeautifulSoup(text,'lxml')

def detail(description, status='Pre-auction Marketing', price='Starting bid: £250,000'):
    return page(f'''<h1>Commercial Property</h1><div class="p__property__address"><p>1 High Street, AB1 2CD</p></div>
    <div class="c__property__status c__property__status--sold">{status}</div>
    <div class="p__property__price"><li class="priceGuide">{price}</li></div>
    <meta property="og:image" content="https://example.org/source-primary.jpg">
    <div id="property-overview"><div class="p__readmore__wrap"><p>{description}</p>
    <h4>Auctioneer comments</h4><p>Reservation fee 4.5% including VAT. Register to bid.</p></div></div>''')

def test_source_primary_status_and_fee_boilerplate():
    lot=c.parse_detail(detail('A freehold shop investment with a current rent of £25,000 per annum.'),URL+'?search_id=tracking')
    assert lot.url==URL and lot.status=='CURRENT'  # the CSS class misleadingly says sold
    assert lot.image_is_primary and lot.image_url.endswith('source-primary.jpg')
    assert 'Reservation fee' not in lot.description and 'Register' not in lot.description
    assert lot.guide_price==250000 and lot.gross_yield==10
    assert lot.vat_status=='UNKNOWN'

def test_historic_rent_and_current_bid_are_not_yield_inputs():
    lot=c.parse_detail(detail('A vacant freehold shop, previously let at £25,000 per annum.',price='Current bid: £200,000'),URL)
    assert lot.guide_price is None and lot.annual_rent is None and lot.gross_yield is None
    assert lot.historic_rent==25000

def test_whole_property_income_overrides_flat_subtotal_and_range_survives():
    lot=c.parse_detail(detail('Mixed-use freehold investment. The commercial premises are currently let at £106,125 per annum. '
        'The flats generate a total annual rental income of £104,000. The entire property producing a gross annual rental income of £210,125 per annum.',
        price='Starting bid: £3,500,000–£3,750,000'),URL)
    assert lot.annual_rent==210125 and lot.gross_yield==6.0
    assert lot.guide_price_upper==3750000

def test_hypothetical_development_income_is_not_current_rent():
    lot=c.parse_detail(detail('A mixed-use development plot. The combined annual rental income would come to around £175,000 per annum once constructed.'),URL)
    assert lot.annual_rent is None and lot.gross_yield is None
    assert lot.potential_income==175000

def test_current_use_outweighs_neighbourhood_and_former_use():
    lot=c.parse_detail(detail('A plot with planning permission for a three bedroom residential dwelling. The nearby marina has a restaurant and shops.'),URL)
    lot.property_type='Development Land'
    assert c.classification(lot) is False
    lot=c.parse_detail(detail('A freehold property with planning permission for 3 flats. Previously the property was used for office space and is ready for conversion.'),URL)
    assert c.classification(lot) is False
    lot=c.parse_detail(detail('A ground floor commercial premises and a two bedroom first floor flat. Currently occupied as a shop and residential accommodation.'),URL)
    lot.property_type='House'
    assert c.classification(lot) is True and lot.property_type=='Mixed Use'

def test_curated_description_does_not_lose_intro_at_a_later_heading():
    from collectors.core import clean_description
    text='A freehold shop investment with accommodation above, let to an established tenant on a current lease. Description: The property includes a yard.'
    assert clean_description(text).startswith('A freehold shop investment')

def test_terminal_status_is_preserved_and_residential_detail_excluded(monkeypatch):
    other=URL.replace('a'*32,'b'*32)
    monkeypatch.setattr(c,'discover',lambda:([URL,other],[],[]))
    monkeypatch.setattr(c,'_safe_fetch',lambda u:detail('A freehold shop investment let to a local business with ground floor retail premises.',status='Sold Prior') if u==URL else detail('A two bedroom residential flat with vacant possession and a private garden.'))
    result=c.collect_iamsold()
    assert len(result.lots)==1 and result.lots[0].status=='SOLD PRIOR'
    assert result.reconciliation['residential_exclusions']==1
    assert result.reconciliation['detail_pages_inspected']==2

def test_failed_detail_does_not_claim_authoritative_zero(monkeypatch):
    monkeypatch.setattr(c,'discover',lambda:([URL],[],[]))
    monkeypatch.setattr(c,'_safe_fetch',lambda u:ValueError('source unavailable'))
    result=c.collect_iamsold()
    assert result.status=='DEGRADED' and not result.authoritative_snapshot
    assert result.reconciliation['current_catalogue_detected'] is True
    assert result.reconciliation['detail_failures']==1

def test_every_category_page_is_traversed_and_duplicate_pages_flagged(monkeypatch):
    card=lambda identity:f'<div class="c__property__address"><h3><a href="/property/{identity*32}/">Lot</a></h3></div>'
    def fetch(url,params=None):
        if params is None: return page('<select name="property_style">'+''.join(f'<option value="{i}">{n}</option>' for i,n in enumerate(c.CATEGORIES,1))+'</select>'),url
        return page('<h1>Properties available Nationally</h1>'+card('a')+'<a class="page-number">2</a>'),c.BASE+'/properties/all/?search_id=token'
    calls=[]
    def subsequent(url):
        calls.append(url)
        return page(card('b'))
    monkeypatch.setattr(c,'fetch',fetch);monkeypatch.setattr(c,'_safe_fetch',subsequent)
    urls,scopes,errors=c.discover()
    assert len(urls)==2 and len(calls)==4 and not errors
    assert all('/page/2/?search_id=token' in url for url in calls)
    monkeypatch.setattr(c,'_safe_fetch',lambda u:page(card('a')))
    assert len(c.discover()[2])==4


def test_advertised_total_and_actual_page_size_override_excess_pager(monkeypatch):
    cards=lambda start:''.join(f'<div class="c__property__address"><h3><a href="/property/{n:032x}/">Lot</a></h3></div>' for n in range(start,start+12))
    def fetch(url,params=None):
        if params is None:return page('<select name="property_style"><option value="1">Commercial Property</option></select>'),url
        return page('<h1>Properties available Nationally</h1><p>132 results</p>'+cards(0)+'<a class="page-number">14</a>'),c.BASE+'/properties/all/?search_id=test'
    calls=[]
    def subsequent(url):
        calls.append(url)
        number=int(url.split('/page/')[1].split('/')[0])
        return page(cards((number-1)*12))
    monkeypatch.setattr(c,'CATEGORIES',('Commercial Property',))
    monkeypatch.setattr(c,'fetch',fetch);monkeypatch.setattr(c,'_safe_fetch',subsequent)
    urls,scopes,errors=c.discover()
    assert len(urls)==132 and len(calls)==10 and not errors
    assert scopes[0]['pages']==11 and scopes[0]['advertised_lots']==132
