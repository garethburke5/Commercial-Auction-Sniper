"""Public snapshots must remain useful, anonymous and independent of paid work."""
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from web_platform.free_snapshot import build_snapshot, eligible
from web_platform.catalogue import Catalogue
from web_platform.site import Site, HERE


def lot(**changes):
    return dict({'source': 'Example Auctions', 'url': 'https://example.com/lot/1',
                 'address': '1 High Street', 'postcode': 'AB1 2CD', 'auction_date': '2099-10-01',
                 'description': 'A ground floor shop with two flats above. The property is fully let. '*4,
                 'annual_rent': 26700, 'guide_price': 190000, 'tenure': 'Freehold',
                 'occupation': 'Let', 'indexable': True}, **changes)


def test_price_range_yield_and_sold_price_remain_distinct():
    s = build_snapshot(lot(guide_price_upper=200000))
    assert s['price'] == '£190,000–£200,000'
    assert s['yield'] == '13.35–14.05%'
    assert 'lower yield uses the £200,000 upper guide' in s['intro'][1]
    s = build_snapshot(lot(status='SOLD', sale_price=180000))
    assert s['price_label'] == 'Reported sale price' and s['yield'] == '14.83%'
    assert build_snapshot(lot(sale_price=180000))['price'] == '£190,000'
    assert build_snapshot(lot(guide_price_upper=180000))['yield'] == 'Not calculable'


@pytest.mark.parametrize('changes', [
    {'occupation': 'Vacant possession'}, {'annual_rent': None}, {'annual_rent': True},
    {'annual_rent': float('nan')}, {'annual_rent': float('inf')}, {'annual_rent': -100},
    {'rent_basis': 'estimated'}, {'rent_basis': 'historic'},
    {'description': 'Previously let at £26,700 per annum. Now vacant.', 'occupation': 'Vacant'},
])
def test_non_passing_income_never_becomes_a_current_yield(changes):
    s = build_snapshot(lot(**changes))
    assert s['yield'] == 'Not calculable'
    assert s['components'] == [] and not s['insights']


def test_source_yield_discrepancy_not_our_computed_yield_or_net_yield():
    s = build_snapshot(lot(description='Gross yield of 18%.', gross_yield=14.05))
    assert s['insights'][0][0] == 'Advertised yield differs from the calculation'
    assert '14.05%' in s['insights'][0][1]
    for description in ('Gross yield 14%.', 'Net yield of 18%.', 'Target gross yield of over 15%.'):
        assert all('differs' not in title for title, _ in build_snapshot(lot(description=description))['insights'])
    assert all('differs' not in title for title, _ in build_snapshot(lot(description='Gross yield 13.5%.',guide_price_upper=200000))['insights'])


def test_only_reconciled_unit_income_can_explain_concentration():
    components = [{'label': 'Main shop', 'annual_rent': 20000}, {'label': 'Other units', 'annual_rent': 6700}]
    s = build_snapshot(lot(income_components=components))
    assert s['components'][0]['share'] == 74.9
    assert '£6,700 a year' in s['insights'][0][1]
    assert not build_snapshot(lot(annual_rent=40000,income_components=components))['components']
    assert not build_snapshot(lot(income_components=[{'label': 'Shop','annual_rent': True}]))['components']


def test_banked_marketing_giy_is_checked_without_replacing_tenancy_facts():
    s = build_snapshot(lot(annual_rent=10616, guide_price=70000), published_sections=[
        {'title':'Key investment points','text':'Investment let at £10,616 per annum (14.15% GIY on Guide Price)'}])
    assert s['yield'] == '15.17%'
    assert s['insights'][0][0] == 'Advertised yield differs from the calculation'
    assert '14.15%' in s['insights'][0][1] and '15.17%' in s['insights'][0][1]
    assert 'two flats above' in str(s['sections'])


def test_fee_subtotal_does_not_claim_all_in_cost_or_use_wrong_price():
    fee = {'amount': 3000, 'upper': 3200, 'basis': 'Published tariff',
           'sources': [{'url': 'javascript:alert(1)', 'label': 'Unsafe'}, {'url': 'https://example.com/fees', 'label': 'Buyer fees'}]}
    s = build_snapshot(lot(guide_price_upper=200000), fee)
    assert s['costs']['subtotal'] == '£193,000–£203,200'
    assert len(s['sources']) == 2
    assert build_snapshot(lot(status='SOLD',sale_price=180000),fee)['costs'] is None
    assert build_snapshot(lot(guide_price_upper=200000),{'amount': 3000})['costs'] is None


def test_public_projection_excludes_private_findings_and_does_not_imply_missing_epc():
    s = build_snapshot(lot(private_report={'findings':'SECRET'}, findings=['SECRET'], legal_pack='SECRET', owner_notes='SECRET'))
    assert 'SECRET' not in json.dumps(s)
    assert s['address'] == '1 High Street, AB1 2CD'
    assert 'No Energy Performance Certificate (EPC) details were captured' in ' '.join(s['gaps'])
    assert not build_snapshot(lot(annual_rent=None,guide_price=None,description='Shop'))['indexable']
    assert not eligible(lot(url='javascript:alert(1)'))


@pytest.fixture
def public_site(tmp_path):
    data = tmp_path/'data'
    (data/'auction_history').mkdir(parents=True)
    (data/'properties.json').write_text(json.dumps({'generated_at':'2026-10-19', 'properties':[
        lot(), lot(url='https://example.com/lot/2', address='2 High Street',description='Shop',annual_rent=None,guide_price=None)]}))
    (data/'auction_history/progress.json').write_text('{"individual_lot_records_captured":0,"by_sector":{"commercial":0,"mixed-use":0}}')
    return Site(Catalogue(tmp_path), 'https://example.org/auction')


def test_standalone_page_safe_links_sources_at_end_and_no_backend_dependencies(public_site, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A public snapshot must not start research or load history')
    monkeypatch.setattr(public_site.market, 'for_property', forbidden)
    monkeypatch.setattr(public_site.catalogue, 'history', forbidden)
    row = public_site.catalogue.all_properties[0]
    row['tenant'] = '<script>alert(1)</script>'
    for _ in range(3):
        html = public_site.snapshot_page(row)
        soup = BeautifulSoup(html, 'html.parser')
        assert soup.select_one('link[rel=canonical]')['href'] == public_site.origin + row['snapshot_path']
        assert '<script>alert' not in html
        assert [s['src'].split('?')[0] for s in soup.select('script[src]')] == ['/auction/static/snapshot.js']
        assert not soup.select('iframe, form, img, video, audio, link[rel=preconnect]')
        assert soup.select_one('main > footer .sources')
        assert not any(soup.select(f'section:not(.sources) a[href^="https://example.com"]'))
    script = (HERE/'static/snapshot.js').read_text()
    assert 'window.print()' in script
    assert not any(s in script for s in ('fetch(', 'XMLHttpRequest', 'sendBeacon', 'WebSocket', '/api/'))


def test_snapshot_routes_listing_links_and_sitemap(public_site):
    pages = dict(public_site.routes())
    row, thin = public_site.catalogue.all_properties
    assert row['snapshot_path'] in pages
    assert 'href="/auction'+row['snapshot_path']+'"' in pages[row['path']]
    assert public_site.origin+row['snapshot_path'] in public_site.sitemap(pages)
    assert public_site.origin+thin['snapshot_path'] not in public_site.sitemap(pages)
    assert 'noindex,follow' in pages[thin['snapshot_path']]


def test_anonymous_repeated_requests_never_start_paid_provider(public_site, monkeypatch):
    from fastapi.testclient import TestClient
    from web_platform.app import create_app
    monkeypatch.delenv('PRIVATE_API_ONLY', raising=False)
    app = create_app(public_site)
    calls = []
    def provider():
        calls.append(True)
        raise AssertionError('Free snapshot invoked the paid provider')
    app.state.acquisition_provider_factory = provider
    with TestClient(app) as client:
        path = public_site.catalogue.all_properties[0]['snapshot_path']
        for _ in range(3):
            response = client.get(path)
            assert response.status_code == 200 and '£26,700' in response.text
        assert client.get('/static/snapshot.js').status_code == 200
    assert calls == []


def test_static_export_contains_html_and_print_assets_without_pdfs(public_site, tmp_path, monkeypatch):
    from web_platform import export as exporter
    monkeypatch.setattr(exporter, 'Site', lambda **kwargs: public_site)
    out = tmp_path/'export'
    exporter.export(out, public_site.origin)
    row = public_site.catalogue.all_properties[0]
    assert (out/row['snapshot_path'].strip('/')/'index.html').is_file()
    assert (out/'static/snapshot.js').is_file()
    assert not list(out.rglob('*.pdf'))
