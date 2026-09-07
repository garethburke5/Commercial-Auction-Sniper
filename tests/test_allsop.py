import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup

from collectors.allsop import (
    _card_is_target, _extract_targets, _address_from_soup, _header_auction_date,
    _live_status_probe, _page_auction_dates, _date_for_card, _teaser_address,
    _teaser_lot, _allsop_image, _main_identity, _hydrate,
)


class AllsopCollectorTests(unittest.TestCase):
    def test_current_landing_card_without_hyphen_is_commercial(self):
        self.assertTrue(_card_is_target("Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Substantial Freehold Retail Investment Guide Price £5.8M"))

    def test_residential_catalogue_mixed_use_card_is_target(self):
        card="Residential LOT 66 - Sep 2026 London SW5 INVESTMENT - Freehold Well Located Five Storey Mixed Use Building Guide Price £1.1M+"
        self.assertTrue(_card_is_target(card))

    def test_residential_catalogue_mixed_use_exact_page_is_hydrated(self):
        html='''<main><h2>LOT 66 - London</h2><p>7 Kenway Road, Earls Court, London, SW5 0RP</p><h1>INVESTMENT - Freehold Well Located Five Storey Mixed Use Building</h1><p>Residential - 16th &amp; 17th Sept 2026 - Live Stream</p><p>Extending to a total GIA of approximately 2,953 sq ft. Ground and Basement Floors - Retail Unit and Storage - Vacant. First, Second and Third Floors - Four Bedroom Triplex HMO Unit - Subject to an Assured Periodic Tenancy. Current Rent Reserved £45,000 p.a. Freehold.</p></main>'''
        fake=BeautifulSoup(html,"lxml")
        meta={"card":"Residential LOT 66 - Sep 2026 London SW5 Mixed Use Building","image":None,"auction_date":"2026-09-16","card_target":True}
        with patch('collectors.allsop.soup',return_value=fake):
            lot=_hydrate(("https://www.allsop.co.uk/lot-overview/example/r260917-247",meta),today=date(2026,9,7))
        self.assertIsNotNone(lot)
        self.assertEqual(lot.auction_date,"2026-09-16")
        self.assertEqual(lot.address,"7 Kenway Road, Earls Court, London, SW5 0RP")
        self.assertEqual(lot.annual_rent,45000.0)
        self.assertEqual(lot.occupation,"Part vacant / part let")

    def test_extracts_lot_overview_from_canonical_landing_markup(self):
        html='''<section><p>Next commercial auction 7th October 2026</p><article><div>Commercial LOT - Oct 2026</div><div>FEATURED LOT</div><h3>Sheffield S10</h3><p>Substantial Freehold Retail, Supermarket &amp; Car Park Investment</p><img src="/media/auction/lot-44.jpg" alt="Sheffield investment" /><a href="/lot-overview/substantial-freehold-retail-supermarket-car-park-investment-in-sheffield/c261001-044">View lot</a></article></section>'''
        found={};_extract_targets(BeautifulSoup(html,"lxml"),found)
        self.assertEqual(len(found),1);url=next(iter(found))
        self.assertIn("Commercial LOT - Oct 2026",found[url]["card"])
        self.assertEqual(found[url]["image"],"https://www.allsop.co.uk/media/auction/lot-44.jpg")
        self.assertEqual(found[url]["auction_date"],"2026-10-07")

    def test_css_gallery_image_beats_logo(self):
        s=BeautifulSoup('''<html><head><meta property="og:image" content="/media/logo-social.png"></head><body><div class="hero" style="background-image:url('/media/property/c261001-044/hero-large.webp')"></div><img src="/media/logo.png" alt="Allsop logo"></body></html>''','lxml')
        image=_allsop_image(s,'https://www.allsop.co.uk/lot-overview/example/c261001-044')
        self.assertTrue(image is None or "logo" not in image.lower())

    def test_rejects_pure_residential_card(self):
        self.assertFalse(_card_is_target("Residential LOT 12 - Sep 2026 Two Bedroom Flat London SW1"))

    def test_address_uses_current_main_lot_not_related_card(self):
        html='''<body><aside><h3>Featured</h3><p>Sheffield S10 2AA</p></aside><main><h2>LOT 66 - London</h2><p>7 Kenway Road, Earls Court, London, SW5 0RP</p><h1>INVESTMENT - Freehold Well Located Five Storey Mixed Use Building</h1></main></body>'''
        s=BeautifulSoup(html,"lxml")
        self.assertEqual(_address_from_soup(s,"Commercial LOT Oct 2026 Sheffield S10"),"7 Kenway Road, Earls Court, London, SW5 0RP")
        lot,address,_=_main_identity(s)
        self.assertEqual(lot,"Lot 66");self.assertIn("SW5 0RP",address)

    def test_catalogue_header_date_is_parsed(self):
        self.assertEqual(_header_auction_date("Residential - 16th & 17th Sept 2026 - Live Stream"),"2026-09-16")

    def test_page_dates_match_month_only_teaser_to_real_auction_day(self):
        s=BeautifulSoup('<main><p>Wednesday 7th October 2026</p><p>Wednesday 11th November 2026</p></main>',"lxml")
        dates=_page_auction_dates(s,today=date(2026,9,6))
        self.assertEqual(dates,("2026-10-07","2026-11-11"));self.assertEqual(_date_for_card("Commercial LOT - Oct 2026",dates),"2026-10-07")

    def test_generic_page_chrome_sold_prior_does_not_enter_status_probe(self):
        s=BeautifulSoup('<body><footer>Other auction results include sold prior lots.</footer><main><h2>LOT 1 - London</h2><p>1 High Street, London, W1A 1AA</p><h1>Retail Investment</h1></main></body>',"lxml")
        self.assertNotIn("sold prior",_live_status_probe(s,"irrelevant card").lower())

    def test_future_featured_teaser_uses_exact_published_auction_date(self):
        card="Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Substantial Freehold Retail, Supermarket & Car Park Investment Guide Price £5.8M"
        self.assertEqual(_teaser_address(card),"Sheffield S10")
        lot=_teaser_lot("https://www.allsop.co.uk/lot-overview/example/c261001-044",card,"https://www.allsop.co.uk/media/auction/lot-44.jpg","2026-10-07")
        self.assertEqual(lot.auction_date,"2026-10-07")

    def test_exact_detail_date_rejects_historic_lot_even_if_future_card_is_contaminated(self):
        html='''<main><h2>LOT 67 - Bolton</h2><p>26-38 Bridge Street, Bolton, Lancashire, BL1 2EH</p><h1>Freehold Retail Ground Rent Investment</h1><p>Commercial - 24th March 2026 - Live Stream</p><p>Guide Price £600,000 Current Rent Reserved £40,950 p.a. Freehold</p></main>'''
        fake=BeautifulSoup(html,"lxml")
        meta={"card":"Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Retail Investment","image":None,"auction_date":"2026-10-07","card_target":True}
        with patch('collectors.allsop.soup',return_value=fake):
            self.assertIsNone(_hydrate(("https://www.allsop.co.uk/lot-overview/old/c260324-100",meta),today=date(2026,9,7)))

    def test_exact_detail_identity_overrides_unrelated_future_teaser(self):
        html='''<main><h2>LOT 44 - Sheffield</h2><p>123 Ecclesall Road, Sheffield, S10 1AA</p><h1>Substantial Freehold Retail Supermarket & Car Park Investment</h1><p>Commercial - 7th October 2026 - Live Stream</p><p>Guide Price £5,800,000 Current Rent Reserved £450,000 p.a. Freehold</p><img src="/media/property/lot44.jpg" alt="property"></main>'''
        fake=BeautifulSoup(html,"lxml")
        meta={"card":"Commercial LOT - Oct 2026 FEATURED LOT Darwen BB3 Another Investment Lot 113","image":None,"auction_date":"2026-10-07","card_target":True}
        with patch('collectors.allsop.soup',return_value=fake):
            lot=_hydrate(("https://www.allsop.co.uk/lot-overview/sheffield/c261001-044",meta),today=date(2026,9,7))
        self.assertEqual(lot.address,"123 Ecclesall Road, Sheffield, S10 1AA");self.assertEqual(lot.lot_number,"Lot 44");self.assertEqual(lot.auction_date,"2026-10-07")


if __name__=="__main__": unittest.main()
