import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup

from collectors import harman_healy, lsh, mchugh, town_country


class FirstPartyRouteFallbackTests(unittest.TestCase):
    def test_lsh_discovery_uses_homepage_when_future_route_fails(self):
        html='''<html><body><h1>Next Auction</h1><a href="/lot/details/abc">Lot</a></body></html>'''
        def fake(url):
            if url.endswith('/future-auctions'):
                raise RuntimeError('route reset')
            return BeautifulSoup(html,'lxml')
        with patch.object(lsh,'_resilient_soup',side_effect=fake):
            soup,url=lsh._discovery_soup()
        self.assertEqual(url,lsh.BASE + '/')
        self.assertIn('/lot/details/abc',str(soup))

    def test_mchugh_landing_rediscovers_canonical_current_catalogue(self):
        landing=BeautifulSoup('<a href="/future-auctions/99999">View current lots</a>','lxml')
        catalogue=BeautifulSoup('<a href="/lot/details/123">Lot 123</a>','lxml')
        def fake(url):
            if url == mchugh.URL:
                raise RuntimeError('direct reset')
            if '/future-auctions/99999' in url:
                return catalogue
            return landing
        with patch.object(mchugh,'_fetch',side_effect=fake):
            soup,url=mchugh._catalogue_soup()
        self.assertTrue(url.endswith('/future-auctions/99999'))
        self.assertIn('/lot/details/123',str(soup))

    def test_town_country_diary_keeps_published_future_catalogues_only(self):
        html='''<table>
        <tr><td>26th August 2026</td><td><a href="/future-auctions/old">View Lots</a></td></tr>
        <tr><td>29th September 2026</td><td><a href="/future-auctions/live">View Lots</a></td></tr>
        </table>'''
        s=BeautifulSoup(html,'lxml')
        links=town_country._future_catalogue_links('https://south.townandcountrypropertyauctions.co.uk',s)
        self.assertEqual(links,['https://south.townandcountrypropertyauctions.co.uk/future-auctions/live'])

    def test_harman_current_catalogue_date_comes_from_future_lot_headings(self):
        future=(date.today().replace(year=max(date.today().year, 2026))).strftime('%d/%m/%Y')
        # Keep the fixture future-proof if the suite is run after the 2026 catalogue.
        if date.today() > date(2026,9,17):
            future='17/09/2099'
        html=f'<h3>Online: Lot 1 | End Time - {future} 10:30</h3>'
        d=harman_healy._current_catalogue_date(BeautifulSoup(html,'lxml'))
        self.assertIsNotNone(d)
        self.assertGreaterEqual(d,date.today())


if __name__ == '__main__':
    unittest.main()
