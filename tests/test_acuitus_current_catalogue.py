from bs4 import BeautifulSoup
from collectors import acuitus


def card(n=1, day='29/10/2099', sector='Retail', status='Available', guide='£400,000'):
    return f'<a href="/property/{n}/"><span class="proplist-grid-address">{n} High Street AB1 2CD</span><span class="proplist-sector">{sector}</span><dl class="proplist-grid-status"><dt>Auction</dt><dd>{day}</dd><dt>Lot</dt><dd>{n}</dd><dt>Status</dt><dd>{status}</dd><dt>Guide*</dt><dd>{guide}</dd></dl></a>'


def detail(day='29th October 2099',status='Available',use='Bank',description='The property comprises a ground floor banking hall with offices above.'):
    return f'''<main><h1>26 The Broadway, Liverpool L11 1DA</h1><p>Lease renewed; previous rent £40,000 p.a.</p>
    <ul class="specifics"><li><span>Lot</span>1</li><li><span>Auction</span>{day}</li><li><span>Rent</span>£38,000 per Annum Exclusive</li><li><span>Status</span>{status}</li><li><span>Guide*</span>£400,000 - £425,000</li><li><span>Sector</span>{use}</li></ul>Interested? Register to bid</main>
    <div class="propinfo info"><p>Property Information</p><p>Tenure Virtual Freehold. For 999 years from 1947.</p><p>Description {description}</p><p>VAT VAT is not applicable to this lot.</p><p>EPC Band B.</p></div>
    <div class="propinfo tenancy"><h3>Tenancy &amp; Accommodation</h3><table><tr><th>Floor</th><th>Use</th><th>Floor Areas sq m</th><th>Floor Areas sq ft</th><th>Tenant</th><th>Term</th><th>Rent Review</th><th>Rent p.a.x.</th></tr><tr><td>Ground/First</td><td>Bank/Office</td><td>262.70</td><td>(2,828)</td><td>LLOYDS BANK PLC</td><td>7 years from 19/12/2022</td><td>19/12/2026</td><td>£38,000</td></tr><tr><td colspan="2">Total</td><td>262.70</td><td>(2,828)</td><td colspan="4">£38,000</td></tr></table></div>
    <aside>You may also be interested in Retail £900,000</aside>'''


def test_exact_detail_uses_current_rent_external_main_sections_and_range(monkeypatch):
    monkeypatch.setattr(acuitus,'soup',lambda *a,**k:BeautifulSoup(detail(),'lxml'))
    lot=acuitus._rich_lot('https://www.acuitus.co.uk/property/1/','',{'Auction':'29/10/2099'})
    assert lot.auction_date=='2099-10-29' and lot.annual_rent==38000
    assert lot.historic_rent==40000 and lot.guide_price_upper==425000
    assert lot.tenure=='Virtual Freehold' and lot.area_sqft==2828 and lot.epc=='B'
    assert lot.tenant=='LLOYDS BANK PLC' and lot.rent_review=='19/12/2026'
    assert '£900,000' not in lot.description and 'Register to bid' not in lot.description


def test_catalogue_rolls_forward_and_reconciles_all_cards(monkeypatch):
    listing='<p>1 - 2 of 2 properties</p>'+card()+card(2,status='Withdrawn Prior')
    def source(url,**kw):
        return BeautifulSoup(listing if 'find-a-property' in url else detail(status='Withdrawn Prior' if '/2/' in url else 'Available'),'lxml')
    monkeypatch.setattr(acuitus,'soup',source)
    r=acuitus.collect()
    assert r.status=='LIVE' and r.scope_dates==('2099-10-29',)
    assert len(r.lots)==2 and r.lots[1].status=='WITHDRAWN PRIOR'
    assert r.reconciliation['source_lot_count']==r.reconciliation['lots_parsed']==2
    assert r.authoritative_snapshot


def test_all_cards_are_inspected_and_residential_exclusion_is_measured(monkeypatch):
    listing='<p>1 - 1 of 1 properties</p>'+card(sector='Residential')
    residential=detail(use='Residential',description='A detached family house with three bedrooms.').replace('Bank/Office','Residential')
    monkeypatch.setattr(acuitus,'soup',lambda url,**kw:BeautifulSoup(listing if 'find-a-property' in url else residential,'lxml'))
    r=acuitus.collect()
    assert r.lots==[] and r.reconciliation['classification_rejections']==1
    assert r.reconciliation['source_lot_count']==r.reconciliation['lots_parsed']==1


def test_date_conflict_and_unknown_status_prevent_green_collection(monkeypatch):
    listing='<p>1 - 1 of 1 properties</p>'+card()
    for page in [detail(day='17th September 2099'),detail(status='Unexplained')]:
        monkeypatch.setattr(acuitus,'soup',lambda url,**kw:BeautifulSoup(listing if 'find-a-property' in url else page,'lxml'))
        r=acuitus.collect()
        assert r.status=='FAILED' and not r.authoritative_snapshot
        assert r.reconciliation['detail_failures']==1


def test_missing_cards_not_catalogue_pending_and_incomplete_inventory_not_complete():
    cards,total,complete=acuitus.catalogue_cards(BeautifulSoup('<p>1 - 1 of 49 properties</p>'+card(),'lxml'))
    assert len(cards)==1 and total==49 and not complete
