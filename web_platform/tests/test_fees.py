import json
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup
import pytest
from web_platform.fees import load_fees, fee_profile, directory, estimate_fee
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
    assert card.select_one('.metrics') and not card.select_one('.target-price')
    assert 'GIY at guide' in card.get_text() and '10.0%' in card.get_text()
    assert card.select_one('a[href$="#buyer-fees"]')
    assert not card.select_one('details.investment').has_attr('open')
    for page in pages.values():
        html = BeautifulSoup(page, 'html.parser')
        assert not html.select('.card .target, .fee-basis.published, .fee-basis.lot_example')
        assert 'Published buyer terms' not in html.get_text()
        assert 'Example lot terms' not in html.get_text()
    assert index.select_one('.fee-detail') and index.select_one('time[datetime]')
    assert 'View properties & fees' in index.get_text()
    prop = BeautifulSoup(pages[site.catalogue.properties[0]['path']], 'html.parser')
    assert prop.select_one('#property-target').get('value') is None
    assert prop.select_one('.yield-calculator .target-price').get_text() == 'Choose a target yield'
    for path, bundle in site.board_assets():
        if path.startswith('/board/') and not path.endswith('/index.json'):
            for markup in json.loads(bundle).values():
                assert 'target-price' not in markup and 'GIY at guide' in markup


@pytest.mark.parametrize('guide,amount,description', [
    (29999, 250, 'below £30,000'),
    (30000, 2100, 'at or above £30,000'),
    (250000, 2100, 'at or above £30,000'),
])
def test_savills_uses_current_published_amount_without_vat_commentary(guide, amount, description):
    profile = fee_profile('savills-auctions', load_fees())
    fee = estimate_fee({'guide_price': guide}, profile)
    assert fee['amount'] == amount and fee['display'] == f'£{amount:,}'
    assert fee['vat'] == profile['vat_label'] == ''
    assert description in fee['basis']
    assert fee['sources'] == [{'label': 'Official buyer terms', 'url': 'https://auctions.savills.co.uk/buying'}]
    # Provenance and the source's lack of a VAT statement remain in the data.
    assert profile['basis'] == 'published'
    assert profile['calculation']['bands'][0]['vat'] == 'unconfirmed'


@pytest.mark.parametrize('vat,label,total', [
    ('extra', '+ VAT', 1200), ('included', 'Including VAT', 1000),
    ('unconfirmed', '', 1000),
])
def test_fee_display_preserves_published_vat_terms_for_any_auctioneer(vat, label, total):
    profile = {'basis': 'published', 'calculation': {'bands': [{'rate': .01, 'minimum': 1000, 'vat': vat}]}}
    fee = estimate_fee({'guide_price': 50000}, profile)
    assert fee['display'] == '£1,000' and fee['vat'] == label
    assert fee['amount'] == total  # existing arithmetic retains VAT when explicit
    ranged = estimate_fee({'guide_price': 50000, 'guide_price_upper': 150000}, profile)
    assert ranged['display'] == '£1,000–£1,500' and ranged['vat'] == label
    assert ranged['upper'] == total * 1.5


def test_all_auctioneer_profiles_hide_internal_vat_uncertainty_without_losing_terms():
    fees = load_fees()
    for slug, raw in fees.items():
        profile = fee_profile(slug, fees)
        assert profile['basis'] == raw['basis'] and profile['sources'] == raw['sources']
        assert not any(word in profile['vat_label'].lower() for word in ('confirm', 'unverified'))
        if raw['vat'].startswith('Including VAT'):
            assert profile['vat_label'] == raw['vat']


def test_card_markup_changes_invalidate_browser_bundles(tmp_path,monkeypatch):
    from web_platform import site as module
    # Same catalogue but new card markup must not reuse a cached JSON URL.
    class EmptyCatalogue:
        properties=[]
        sources={}
    before=Site(EmptyCatalogue())
    (tmp_path/'templates').mkdir()
    (tmp_path/'static').mkdir()
    for name in ('site.css','board.js','search.js','workspace.js'):
        (tmp_path/'static'/name).write_bytes((module.HERE/'static'/name).read_bytes())
    (tmp_path/'templates/cards.html').write_text('changed card markup')
    monkeypatch.setattr(module,'HERE',tmp_path)
    after=Site(EmptyCatalogue())
    assert before.board_version!=after.board_version
