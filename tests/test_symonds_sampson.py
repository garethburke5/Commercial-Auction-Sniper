import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.symonds_sampson import (
    _event_links, _is_target, _property_links, _parse_date, _image,
    _current_rent, _detail, _property_type,
)


class SymondsSampsonCollectorTests(unittest.TestCase):
    def test_event_date_parser(self):
        self.assertEqual(_parse_date("Thursday, 24 September 2026 2:00 PM - 5:00 PM"), "2026-09-24")

    def test_event_discovery_keeps_all_future_events(self):
        html = """
        <html><body>
          <div><h3>Digby Hall</h3><p>Thursday, 24 September 2026 2:00 PM - 5:00 PM</p><a href='/event/property-auction-sep2026-memorialhall'>View Event</a></div>
          <div><h3>Guildhall</h3><p>Thursday, 08 October 2026 2:00 PM - 5:00 PM</p><a href='/event/property-auction-oct2026-guildhall'>View Event</a></div>
          <div><h3>Old Auction</h3><p>Wednesday, 26 August 2026 2:00 PM - 5:00 PM</p><a href='/event/property-auction-aug2026'>View Event</a></div>
        </body></html>
        """
        events = _event_links(BeautifulSoup(html, "lxml"), today=date(2026, 9, 6))
        self.assertEqual(len(events), 2)
        self.assertEqual(events["https://auctions.symondsandsampson.co.uk/event/property-auction-sep2026-memorialhall"], "2026-09-24")
        self.assertEqual(events["https://auctions.symondsandsampson.co.uk/event/property-auction-oct2026-guildhall"], "2026-10-08")

    def test_property_links_only_take_property_pages(self):
        html = """
        <html><body>
          <a href='/property/dwr0007b9/dt6/bridport/st-andrews-road/other/studio'>For Sale St Andrews Road Guide Price £300,000</a>
          <a href='/property/dwr0007a9/dt9/sherborne/long-street/flat/3-bedrooms'>For Sale Long Street Guide Price £150,000</a>
          <a href='/events/property-auction/foo'>Other event</a>
        </body></html>
        """
        found = _property_links(BeautifulSoup(html, "lxml"), "2026-09-24")
        self.assertEqual(len(found), 2)
        self.assertTrue(all(value[1] == "2026-09-24" for value in found.values()))

    def test_image_prefers_real_property_gallery_over_branding(self):
        html = '''
        <html><head><meta property="og:image" content="https://cdn.webdadi.net/assets/logo.png"></head>
        <body>
          <img src="https://cdn.webdadi.net/static/office-team.jpg" alt="office" />
          <img data-src="https://cdn.webdadi.net/2a8d27ce-3e62-4d24-bf5e-97cb3f7f4a91/property-main.webp" alt="Property image" />
        </body></html>
        '''
        image = _image(BeautifulSoup(html, "lxml"), "https://auctions.symondsandsampson.co.uk/property/example")
        self.assertEqual(image, "https://cdn.webdadi.net/2a8d27ce-3e62-4d24-bf5e-97cb3f7f4a91/property-main.webp")

    def test_image_rejects_site_plan_when_exterior_exists(self):
        html='''<body>
          <img src="https://cdn.webdadi.net/property/beer/site-plan.jpg" alt="Site plan">
          <img src="https://cdn.webdadi.net/property/beer/front-exterior.jpg" alt="Property exterior">
        </body>'''
        image=_image(BeautifulSoup(html,'lxml'),'https://auctions.symondsandsampson.co.uk/property/beer')
        self.assertIn('front-exterior',image)

    def test_commercial_and_mixed_use_are_kept_but_plain_house_is_rejected(self):
        self.assertTrue(_is_target("Grade II Listed public house with living accommodation upstairs and redevelopment potential"))
        self.assertTrue(_is_target("Mixed use retail and residential investment property"))
        self.assertTrue(_is_target("Commercial office building with parking"))
        self.assertTrue(_is_target("Development site with planning permission"))
        self.assertFalse(_is_target("Detached house with four bedrooms and garden requiring modernisation"))
        self.assertFalse(_is_target("Three bedroom flat for sale by auction"))
        self.assertFalse(_is_target("3 Bedroom House For Sale. Incredibly versatile residential refurbishment and redevelopment opportunity with large garage and extensive grounds."))
        self.assertFalse(_is_target("Four bedroom family home with redevelopment potential subject to planning"))

    def test_current_income_is_not_replaced_by_potential_flat_income(self):
        text=("Mixed-use investment property. Ground-floor commercial unit generating £22,500 rent pa. "
              "Three vacant flats above with potential further income of £24,000 pa. Guide Price £295,000.")
        self.assertEqual(_current_rent(text),22500.0)

    def test_commercial_plus_existing_flats_is_mixed_use_without_literal_label(self):
        text="Two existing flats and a shop let at £5,400 pa with garage/workshop/store and extensive grounds."
        self.assertEqual(_property_type(text),"Mixed Use")

    def test_beer_particulars_capture_guide_current_rent_and_development(self):
        html='''
        <html><head><title>Fore Street, Beer, Seaton, Devon EX12 | Symonds</title></head><body><main>
        <h1>Fore Street, Beer, Seaton, Devon EX12</h1>
        <p>Guide Price £295,000</p><p>Tenure Freehold</p>
        <p>Incredibly versatile residential refurbishment and redevelopment opportunity.</p>
        <p>Multiple elements including two existing flats and a shop let at £5,400 pa.</p>
        <p>Multi-vehicle garage/workshop/store. Extensive grounds. 125m from the seafront at Beer.</p>
        <img src="https://cdn.webdadi.net/property/beer/front-exterior.jpg" alt="Property exterior">
        <img src="https://cdn.webdadi.net/property/beer/site-plan.jpg" alt="Site plan">
        </main></body></html>'''
        def fetcher(_): return BeautifulSoup(html,'lxml')
        lot=_detail('https://auctions.symondsandsampson.co.uk/property/beer','3 Bedroom House For Sale shop and flats','2026-10-08',fetcher=fetcher)
        self.assertIsNotNone(lot)
        self.assertEqual(lot.guide_price,295000.0)
        self.assertEqual(lot.annual_rent,5400.0)
        self.assertEqual(lot.tenure,'Freehold')
        self.assertEqual(lot.property_type,'Mixed Use')
        self.assertTrue(lot.development_potential)
        self.assertTrue(lot.refurbishment)
        self.assertTrue(lot.asset_management)
        self.assertIn('front-exterior',lot.image_url)

    def test_axminster_particulars_keep_current_income(self):
        html='''<main><h1>West Street, Axminster, Devon EX13</h1>
        <p>Guide Price £295,000. Freehold mixed-use investment property in central Axminster.</p>
        <p>Ground-floor restaurant generating £22,500 rent pa and three vacant flats above with potential further £24,000 pa.</p>
        <p>Corner town-centre position. Grade II Listed. New roof.</p>
        <img src="https://cdn.webdadi.net/property/axminster/exterior.jpg" alt="Property exterior">
        </main>'''
        def fetcher(_): return BeautifulSoup(html,'lxml')
        lot=_detail('https://auctions.symondsandsampson.co.uk/property/axminster','Mixed-use investment','2026-10-08',fetcher=fetcher)
        self.assertEqual(lot.guide_price,295000.0)
        self.assertEqual(lot.annual_rent,22500.0)
        self.assertEqual(lot.property_type,'Mixed Use')
        self.assertEqual(lot.occupation,'Part let / part vacant')
        self.assertEqual(lot.listed_status,'Grade II Listed')
        self.assertAlmostEqual(lot.gross_yield,7.63,places=2)


if __name__ == "__main__":
    unittest.main()
