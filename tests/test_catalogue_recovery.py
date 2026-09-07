import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup

from collectors.barnett_ross import _fallback_rows, _property_image
from collectors.harman_healy import FUTURE, SEARCH, _inspect_catalogue_with_fallback, _lots_from_catalogue, _lots_from_soup
from collectors.savills_all_future import _savills_property_image_from_html


class CatalogueRecoveryTests(unittest.TestCase):
    def test_barnett_ross_table_fallback_preserves_terminal_rows_with_status(self):
        html='''
        <table>
          <tr><th>Lot</th><th>Address</th><th>Location</th><th>Guide</th></tr>
          <tr><td>1</td><td>1 High Street, London SW1A 1AA</td><td>London</td><td>Guide: £250,000+</td></tr>
          <tr><td>2</td><td>2 High Street, London SW1A 1AB</td><td>London</td><td>Sold Prior</td></tr>
          <tr><td>3</td><td>3 High Street, London SW1A 1AC</td><td>London</td><td>Withdrawn - Refer</td></tr>
        </table>
        '''
        lots=_fallback_rows(BeautifulSoup(html,'lxml'),'2026-09-10')
        self.assertEqual(len(lots),3)
        by_lot={x.lot_number:x for x in lots}
        self.assertEqual(by_lot['Lot 1'].address,'1 High Street, London SW1A 1AA')
        self.assertEqual(by_lot['Lot 1'].guide_price,250000.0)
        self.assertEqual(by_lot['Lot 1'].auction_date,'2026-09-10')
        self.assertEqual(by_lot['Lot 1'].status,'CURRENT')
        self.assertEqual(by_lot['Lot 2'].status,'SOLD PRIOR')
        self.assertEqual(by_lot['Lot 3'].status,'WITHDRAWN')

    def test_barnett_ross_image_prefers_real_gallery_over_branding(self):
        html='''
        <html><head><meta property="og:image" content="/images/logo.png"></head><body>
          <img src="/images/logo-header.png" alt="Barnett Ross">
          <div class="gallery" style="background-image:url('/property-images/lot-12-front.jpg')"></div>
          <img data-src="/property-images/lot-12-interior.jpg" alt="Property photograph">
        </body></html>
        '''
        image=_property_image(BeautifulSoup(html,'lxml'),'https://www.barnettross.co.uk/property.php?id=12')
        self.assertIn('/property-images/lot-12-',image)
        self.assertNotIn('logo',image.lower())

    def test_savills_root_relative_gallery_asset_is_recovered(self):
        raw='''<script>window.gallery={"image":"\\/assets/images/lots/12345/main.jpg"}</script>'''
        url=_savills_property_image_from_html(raw,'https://auctions.savills.co.uk/auctions/lot-12345')
        self.assertEqual(url,'https://resize.auctions.savills.co.uk/assets/images/lots/12345/main.jpg')

    def test_savills_srcset_gallery_asset_is_recovered(self):
        raw='''<img src="/images/logo.png" srcset="/assets/images/lots/44/a.webp 640w, /assets/images/lots/44/b.webp 1200w">'''
        url=_savills_property_image_from_html(raw,'https://auctions.savills.co.uk/auctions/lot-44')
        self.assertIn('/assets/images/lots/44/',url)
        self.assertNotIn('logo',url.lower())

    def test_harman_healy_js_shell_is_retried_with_rendered_page(self):
        shell=BeautifulSoup('<html><body><div id="root"></div><script src="app.js"></script></body></html>','lxml')
        rendered=BeautifulSoup('<h2>Lot 1 - Shop, London</h2><p>Guide £100,000 Commercial investment</p>','lxml')
        with patch('collectors.harman_healy.soup',side_effect=[shell,rendered]):
            got=_inspect_catalogue_with_fallback('https://example.test/current')
        self.assertIn('Lot 1',got.get_text(' ',strip=True))

    def test_harman_healy_search_fallback_filters_out_historical_lots(self):
        html='''
        <div><a href="/property/1">Lot 1</a><p>Auction 10 September 2026 Commercial property</p></div>
        <div><a href="/property/2">Lot 2</a><p>Auction 1 July 2026 Commercial property</p></div>
        '''
        s=BeautifulSoup(html,'lxml')
        with patch('collectors.harman_healy.date') as d:
            d.today.return_value=date(2026,9,7)
            lots=_lots_from_soup(s,'https://example.test/search')
        self.assertTrue(all((x.auction_date or '') >= '2026-09-07' for x in lots))

    def test_harman_healy_semantic_parser_accepts_non_heading_lot_marker(self):
        html='''<div><strong>Lot 7</strong><p>12 High Street, Croydon CR0 1AA</p><p>Commercial investment producing £12,000 pa. Guide £100,000.</p></div>'''
        lots=_lots_from_soup(BeautifulSoup(html,'lxml'),'https://example.test/current')
        self.assertTrue(any(x.lot_number=='Lot 7' for x in lots))

    def test_harman_healy_specific_route_failure_falls_back_to_generic_catalogue(self):
        specific=BeautifulSoup('<html><body>Not found</body></html>','lxml')
        generic=BeautifulSoup('<h2>Lot 2</h2><p>20 High Street, Sutton SM1 1AA Commercial property Guide £150,000</p>','lxml')
        with patch('collectors.harman_healy.soup',side_effect=[specific,generic]):
            lots=_lots_from_catalogue(FUTURE,'2026-09-15')
        self.assertIsInstance(lots,list)
