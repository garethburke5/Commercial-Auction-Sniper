from bs4 import BeautifulSoup

from collectors.core import Lot, clean_description
from collectors.symonds_catalogue import INDEX, collect_catalogue, same_property
from collectors.symonds_sampson import _reconcile_catalogue, _brochure_particulars, _structured
from collectors.publication_quality import prepare_publication


def test_public_catalogue_traverses_all_details_before_classifying_and_retains_status():
    index='<table><tr><td><a href="guides.aspx?a=222&c=sym&aid=10">08/10/2099</a></td></tr></table>'
    event='<table class="lot-table"><tbody>'+''.join(
        f'<tr><td><a href="LotDetails.aspx?LotID={n}&a=222&c=sym">{n}</a></td><td>{status}</td></tr>'
        for n,status in [(7,'Sold Prior'),(8,'')])+'</tbody></table>'
    def page(address,description,income):
        return f'<h3>{address}</h3><p>{description}</p><img alt="Lot image." src="https://example.test/hero.jpg"><table class="extra-details"><tr><td>Guide Price *</td><td>£25,000–£50,000</td></tr><tr><td>Income</td><td>{income}</td></tr></table>'
    calls=[]
    def fetch(url):
        calls.append(url)
        raw=index if url==INDEX else event if 'aid=' in url else page(
            'Marine Cottage, Fore Street, Beer, EX12 3EE' if 'LotID=7' in url else 'Example House',
            'Freehold Mixed Use Building Shop Let & Two Flats' if 'LotID=7' in url else 'Freehold Detached House Four Bedroom With Workshop',
            '£5,400 per annum' if 'LotID=7' in url else '')
        return BeautifulSoup(raw,'lxml')
    entries,telemetry=collect_catalogue(fetcher=fetch)
    assert telemetry['inspected']==telemetry['discovered']==2
    assert len(calls)==4
    lots,reconciled=_reconcile_catalogue([],entries,[])
    assert len(lots)==len(reconciled)==1
    assert lots[0].status=='SOLD PRIOR'
    assert (lots[0].guide_price,lots[0].guide_price_upper,lots[0].annual_rent)==(25000,50000,5400)
    assert len(prepare_publication({'properties':[lots[0].to_dict()]})['properties'])==1


def test_reconciliation_keeps_source_primary_and_one_lot():
    url='https://auctions.symondsandsampson.co.uk/property/dwr000784/ex12/beer/fore-street/house/3-bedrooms'
    old={'source':'Symonds & Sampson','url':url,'address':'Fore Street Beer, Seaton, Devon, EX12',
         'auction_date':'2099-10-08','image_url':'https://example.test/source-primary.jpg'}
    live=Lot(old['source'],url,old['address'],auction_date=old['auction_date'],
             image_url=old['image_url'],description='Mixed use building, shop and flats.',status='WITHDRAWN')
    entry={'url':'https://auctioneertemplates.eigroup.co.uk/LotDetails.aspx?a=222&LotID=7',
           'address':'Marine Cottage, Fore Street, Beer, Seaton, EX12 3EE','description':'Mixed use building. Shop let and two flats.',
           'auction_date':'2099-10-08','lot_number':'Lot 7','status':'CURRENT','annual_rent':5400,
           'image_url':'https://example.test/eig-primary.jpg'}
    lots,_=_reconcile_catalogue([live],[entry],[old])
    assert len(lots)==1
    assert lots[0].image_url==old['image_url']
    assert lots[0].url==url
    assert lots[0].status=='WITHDRAWN'
    assert not same_property('Other Street, Seaton, EX12 3EE',old['address'])


def test_bid_instruction_before_brochure_particulars_does_not_erase_tenancy():
    text='Mixed-use investment. '+('Property introduction. '*12)+'Register to bid in the room, online, by telephone or by proxy via our website. THE PROPERTY Restaurant let on a commercial lease for a 10 year term from 10 May 2023 at an annual rent of £22,500 on an internal repairing and insuring basis. AUCTION CONDITIONS OF SALE VAT fees apply.'
    cleaned=clean_description(_brochure_particulars(text))
    assert '10 May 2023' in cleaned
    assert 'VAT fees' not in cleaned
    assert _structured(cleaned)['fri'] is False


def test_brochure_recovery_keeps_break_and_conditional_erv_separate():
    fore=_structured('Shop let at £5,400pa, new ten-year lease with Y5 mutual breakout provision.')
    assert fore['lease_term']=='10 years'
    assert fore['break_clause']=='Mutual break at year 5'
    west=_structured('The ERV of the apartments, once refurbishment is complete is estimated to be approximately £24,000 per annum.')
    assert west['erv']==24000
