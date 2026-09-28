import json
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup
import pytest
from web_platform.fees import load_fees, fee_profile, directory
from web_platform.catalogue import Catalogue
from web_platform.site import Site


def test_fee_evidence_requires_sources_and_named_lot_examples(tmp_path):
    fees=load_fees()
    assert len(fees)==31
    for slug,fee in fees.items():
        assert fee['checked_on']=='2026-09-28'
        if slug.startswith('auction-house-'):
            assert fee['basis']=='lot_example' and fee['example']
    broken=dict(fees['auction-house-wales']);broken.pop('example')
    path=tmp_path/'fees.json'
    path.write_text(json.dumps({'schema_version':1,'auctioneers':{'bad':broken}}))
    with pytest.raises(ValueError,match='named example'):load_fees(path)
    broken=dict(fees['allsop-commercial']);broken['sources']=[{'label':'Terms','url':'javascript:alert(1)'}]
    path.write_text(json.dumps({'schema_version':1,'auctioneers':{'bad':broken}}))
    with pytest.raises(ValueError,match='Invalid buyer-fee source'):load_fees(path)


def test_unknown_and_stale_fees_are_not_reported_as_current_or_free():
    fees=load_fees()
    fresh=fee_profile('allsop-commercial',fees,today=date(2026,9,28))
    assert not fresh['review_due'] and fresh['vat']=='VAT extra'
    assert fee_profile('allsop-commercial',fees,today=date(2027,1,1))['review_due']
    unknown=fee_profile('new-house',fees)
    assert unknown['basis']=='unverified' and unknown['checked_on'] is None
    assert 'Confirm' in unknown['headline'] and '£0' not in unknown['headline']


def test_fee_boundaries_vat_and_extra_charges_preserve_source_distinctions():
    fees=load_fees()
    assert fees['paul-fosh-auctions']['vat']=='Including VAT'
    assert [r['amount'] for r in fees['paul-fosh-auctions']['rules']]==['Minimum £1,500','Minimum £2,400']
    assert '£1,980' in fees['symonds-sampson']['headline']
    assert '£50,000' in fees['symonds-sampson']['notes']
    assert fees['savills-auctions']['vat']=='VAT: confirm with Savills'
    assert fees['pugh-btg-eddisons']['basis']=='lot_example'
    assert 'separate buyer’s contribution' in fees['pugh-btg-eddisons']['notes']
    assert len(fees['auction-house-north-west']['rules'])==2
    assert fees['bidx1']['basis']=='lot_specific'
    assert fees['mchugh-co']['headline']=='£500 / £1,500'


def test_directory_and_house_page_render_same_evidence_without_changing_income(tmp_path):
    (tmp_path/'data/auction_history').mkdir(parents=True)
    data={'source':'Allsop Commercial','url':'https://example.org/lot/1','address':'1 High Street, York',
          'lot_number':'1','auction_date':'2099-01-01','guide_price':100000,'annual_rent':10000,
          'description':'A commercial shop investment. '*15,'tenure':'Freehold','property_type':'Retail'}
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[data],'generated_at':'2026-09-28T08:00:00Z'}))
    (tmp_path/'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':1,'by_sector':{'commercial':1,'mixed-use':0}}))
    site=Site(Catalogue(tmp_path),'https://example.org/site')
    pages=dict(site.routes())
    index=BeautifulSoup(pages['/auctioneers/'],'html.parser')
    detail=BeautifulSoup(pages['/auctioneers/allsop-commercial/'],'html.parser')
    assert index.select_one('#auctioneer-search') and index.select_one('#auctioneer-current')
    assert index.select_one('.auctioneer-card')['data-current']=='1'
    assert index.select_one('.fee-headline').get_text()==detail.select_one('.fee-headline').get_text()
    assert detail.select_one('#buyer-fees')
    assert detail.select_one('.fee-evidence a')['href'].startswith('https://www.allsop.co.uk/')
    assert site.catalogue.properties[0]['giy']==10
    card=BeautifulSoup(pages['/'],'html.parser').select_one('.card')
    assert card.select_one('details.investment .research-links')
    assert card.select_one('.metrics') and card.select_one('.target-price')
    assert card.select_one('a[href$="#buyer-fees"]')
    assert not card.select_one('details.investment').has_attr('open')


def test_card_markup_changes_invalidate_browser_bundles(tmp_path,monkeypatch):
    from web_platform import site as module
    # Same catalogue but new card markup must not reuse a cached JSON URL.
    class EmptyCatalogue:
        properties=[]
        sources={}
    before=Site(EmptyCatalogue())
    (tmp_path/'templates').mkdir()
    (tmp_path/'static').mkdir()
    for name in ('site.css','board.js'):
        (tmp_path/'static'/name).write_bytes((module.HERE/'static'/name).read_bytes())
    (tmp_path/'templates/cards.html').write_text('changed card markup')
    monkeypatch.setattr(module,'HERE',tmp_path)
    after=Site(EmptyCatalogue())
    assert before.board_version!=after.board_version
