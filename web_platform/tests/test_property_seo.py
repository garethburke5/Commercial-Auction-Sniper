import json
from bs4 import BeautifulSoup
import pytest
from web_platform.catalogue import Catalogue
from web_platform.seo import index_exclusions, property_description
from web_platform.search_audit import audit
from web_platform.tests.test_platform import site


@pytest.mark.parametrize('changes', [dict(auction_date=None), dict(tenure=None, annual_rent=None),
                                    dict(auction_date=None, tenure=None, annual_rent=None)])
def test_substantial_priced_property_is_indexable_without_date_or_rent(site, changes):
    path = site.catalogue.root / 'data/properties.json'
    snapshot = json.loads(path.read_text())
    snapshot['properties'][0].update(changes)
    path.write_text(json.dumps(snapshot))
    row = next(r for r in Catalogue(site.catalogue.root).all_properties if r['guide_price'] == 100000)
    assert row['indexable']
    assert row['index_exclusions'] == []


def test_thin_and_factless_pages_stay_excluded():
    assert index_exclusions({'description': 'A shop', 'guide_price': 50000}) == ['insufficient_particulars']
    row = {'description': 'Property details. ' * 30, 'guide_price': float('nan'), 'tenure': 'Not stated'}
    assert index_exclusions(row) == ['insufficient_property_facts']
    row.update(address='Marketing text instead of an address ' * 10, guide_price=50000)
    assert index_exclusions(row) == ['unusable_address']


def test_rendered_metadata_canonicals_links_and_premium_protection(site):
    pages = dict(site.routes())
    row = site.catalogue.properties[0]
    soup = BeautifulSoup(pages[row['path']], 'html.parser')
    assert soup.h1.get_text(strip=True) == row['address']
    assert soup.title.text == row['address'] + ' — Auction details | Auction Geek'
    assert row['address'] in soup.select_one('meta[name=description]')['content']
    assert '£100,000–£125,000' in soup.select_one('meta[name=description]')['content']
    assert 'max-image-preview:large' in soup.select_one('meta[name=robots]')['content']
    schema = json.loads(soup.select_one('script[type="application/ld+json"]').string)
    assert schema[0]['about']['address'] == row['address']
    assert schema[0]['hasPart']['isAccessibleForFree'] is False
    assert len(schema[1]['itemListElement']) == 4
    result = audit(site, pages)
    assert result['failures'] == []
    assert result['indexable_property_pages'] == 1
    assert result['excluded_properties'][0]['reasons']


def test_audit_catches_accidental_noindex_and_wrong_canonical(site):
    pages = dict(site.routes())
    row = site.catalogue.properties[0]
    pages[row['path']] = pages[row['path']].replace('index,follow,max-image-preview:large', 'noindex,follow').replace(
        'rel="canonical" href="' + site.origin + row['path'], 'rel="canonical" href="https://wrong.example/')
    problems = {r['problem'] for r in audit(site, pages)['failures']}
    assert 'indexing_directive_mismatch' in problems
    assert 'incorrect_canonical' in problems


def test_audit_detects_orphaned_page(site):
    from urllib.parse import urlsplit
    pages = dict(site.routes())
    row = site.catalogue.properties[0]
    for path in pages:
        if path != row['path']:
            soup = BeautifulSoup(pages[path], 'html.parser')
            for link in soup.select('a[href]'):
                if urlsplit(link['href']).path == site.prefix + row['path']:
                    link['href'] = '#'
            pages[path] = str(soup)
    assert 'no_crawlable_path_from_home' in {r['problem'] for r in audit(site, pages)['failures']}


def test_description_labels_unavailable_lot_and_does_not_invent_dates_or_income():
    row = dict(address='1 Example Road', source='Example Auctions', guide_price=100000,
               guide='£100,000', unavailable=True, status='Withdrawn', annual_rent=None)
    text = property_description(row)
    assert 'Withdrawn.' in text and 'Recorded guide £100,000.' in text
    assert 'Auction listing from Example Auctions.' in text
    assert 'yield' not in text and 'rent' not in text and 'snapshot' not in text


def test_github_mirror_is_crawlable_but_not_indexable_including_snapshots(site):
    from web_platform.site import Site
    from urllib.robotparser import RobotFileParser
    mirror = Site(site.catalogue, 'https://example.github.io/auction-geek')
    pages = dict(mirror.routes())
    for html in pages.values():
        assert 'noindex' in BeautifulSoup(html, 'html.parser').select_one('meta[name=robots]')['content']
    assert '<loc>' not in mirror.sitemap(pages)
    assert 'Sitemap:' not in mirror.robots()
    robots = RobotFileParser(); robots.parse(mirror.robots().splitlines())
    assert robots.can_fetch('Googlebot', mirror.origin + site.catalogue.properties[0]['path'])
    report = audit(mirror, pages)
    assert report['failures'] == []
    assert report['indexable_property_pages'] == 0
    assert report['content_eligible_property_pages'] == 1


def test_main_domain_retains_search_indexing(site):
    from web_platform.site import Site
    main = Site(site.catalogue, 'https://auctiongeek.co.uk')
    row = main.catalogue.properties[0]
    pages = dict(main.routes())
    assert 'noindex' not in BeautifulSoup(pages[row['path']], 'html.parser').select_one('meta[name=robots]')['content']
    assert main.origin + row['path'] in main.sitemap(pages)
    assert audit(main, pages)['failures'] == []
