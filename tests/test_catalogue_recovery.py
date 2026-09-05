import unittest
from bs4 import BeautifulSoup

from collectors.barnett_ross import _fallback_rows
from collectors.savills_all_future import _savills_property_image_from_html


class CatalogueRecoveryTests(unittest.TestCase):
    def test_barnett_ross_table_fallback_excludes_non_live_rows(self):
        html='''
        <table>
          <tr><th>Lot</th><th>Address</th><th>Location</th><th>Guide</th></tr>
          <tr><td>1</td><td>1 High Street, London SW1A 1AA</td><td>London</td><td>Guide: £250,000+</td></tr>
          <tr><td>2</td><td>2 High Street, London SW1A 1AB</td><td>London</td><td>Sold Prior</td></tr>
          <tr><td>3</td><td>3 High Street, London SW1A 1AC</td><td>London</td><td>Withdrawn - Refer</td></tr>
        </table>
        '''
        lots=_fallback_rows(BeautifulSoup(html,'lxml'),'2026-09-10')
        self.assertEqual(len(lots),1)
        self.assertEqual(lots[0].address,'1 High Street, London SW1A 1AA')
        self.assertEqual(lots[0].guide_price,250000.0)
        self.assertEqual(lots[0].auction_date,'2026-09-10')

    def test_savills_root_relative_gallery_asset_is_recovered(self):
        raw='''<script>window.gallery={"image":"\\/assets/images/lots/12345/main.jpg"}</script>'''
        url=_savills_property_image_from_html(raw,'https://auctions.savills.co.uk/auctions/lot-12345')
        self.assertEqual(url,'https://resize.auctions.savills.co.uk/assets/images/lots/12345/main.jpg')

    def test_savills_srcset_gallery_asset_is_recovered(self):
        raw='''<img src="/images/logo.png" srcset="/assets/images/lots/44/a.webp 640w, /assets/images/lots/44/b.webp 1200w">'''
        url=_savills_property_image_from_html(raw,'https://auctions.savills.co.uk/auctions/lot-44')
        self.assertTrue(url.startswith('https://resize.auctions.savills.co.uk/assets/images/lots/44/'))


if __name__=='__main__':
    unittest.main()
