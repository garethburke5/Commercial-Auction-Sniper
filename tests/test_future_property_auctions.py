import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.future_property_auctions import _parse_date, _discover, _page_urls, _commercialish, _card_image, _detail_image


class FuturePropertyAuctionsTests(unittest.TestCase):
    def test_date_parser_accepts_abbreviated_and_full_months(self):
        self.assertEqual(_parse_date("Timed Online Auction - 10 Sep 2026"), date(2026,9,10))
        self.assertEqual(_parse_date("Timed Online Auction - 24 September 2026"), date(2026,9,24))

    def test_commercial_classifier_keeps_explicit_investment(self):
        self.assertTrue(_commercialish("Lot 2 £1,290,000 Commercial Investment full building with retail parade"))
        self.assertTrue(_commercialish("Mixed-use shop with flat above"))
        self.assertFalse(_commercialish("2 Bedroom Flat in Glasgow"))

    def test_pagination_follows_source_offsets(self):
        s=BeautifulSoup('''<a href="catalogue_viewall.asp?offset=21">2</a>
        <a href="catalogue_viewall.asp?offset=42">3</a><a href="/auctions.asp">Auctions</a>''','lxml')
        urls=_page_urls(s,"https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp")
        self.assertIn("https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp?offset=21",urls)
        self.assertIn("https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp?offset=42",urls)
        self.assertEqual(len(urls),2)

    def test_linked_upload_gallery_image_is_recovered(self):
        s=BeautifulSoup('''<article>
          <a href="property_details.asp?id=14516980">Lot 2 £1,290,000 Commercial Investment Timed Online Auction - 10 Sep 2026</a>
          <a class="gallery" href="/upload/small_43917_14516980_IMG_00.jpg"><img src="/images/camera-icon.png"></a>
        </article>''','lxml')
        anchor=s.find('a',href=lambda h:h and 'property_details' in h)
        self.assertEqual(_card_image(anchor,"https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp"),"https://www.futurepropertyauctions.co.uk/upload/small_43917_14516980_IMG_00.jpg")

    def test_detail_gallery_link_beats_branding(self):
        s=BeautifulSoup('''<html><head><meta property="og:image" content="/images/logo.png"></head><body>
        <a href="/upload/small_43917_14516980_IMG_00.jpg">Image</a><img src="/images/logo.png"></body></html>''','lxml')
        image=_detail_image(s,"https://www.futurepropertyauctions.co.uk/property_details.asp?id=14516980")
        self.assertIn('/upload/small_43917_14516980_IMG_00.jpg',image)

    def test_discovery_crawls_interleaved_future_inventory_across_pages(self):
        pages={
            "https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp": '''<html><body>
              <article><a href="property_details.asp?id=100">Lot 2 £1,290,000 OPENING BID Commercial Investment 1 High Street, Glasgow Timed Online Auction - 10 Sep 2026</a></article>
              <article><a href="property_details.asp?id=101">Lot 3 £90,000 2 Bedroom Flat Timed Online Auction - 10 Sep 2026</a></article>
              <a href="catalogue_viewall.asp?offset=21">2</a></body></html>''',
            "https://www.futurepropertyauctions.co.uk/catalogue_viewall.asp?offset=21": '''<html><body>
              <article><a href="property_details.asp?id=102">Lot 15 £35,000 Commercial Investment 2 Main Street, Ayr Timed Online Auction - 24 Sep 2026</a></article>
            </body></html>''',
        }
        def fetcher(url): return BeautifulSoup(pages[url],"lxml")
        targets,dates,total,pages_read=_discover(fetcher=fetcher,today=date(2026,9,7))
        self.assertEqual(total,3)
        self.assertEqual(len(targets),2)
        self.assertEqual(set(dates),{"2026-09-10","2026-09-24"})
        self.assertEqual(pages_read,2)
        self.assertIn("https://www.futurepropertyauctions.co.uk/property_details.asp?id=100",targets)
        self.assertIn("https://www.futurepropertyauctions.co.uk/property_details.asp?id=102",targets)


if __name__ == "__main__":
    unittest.main()
