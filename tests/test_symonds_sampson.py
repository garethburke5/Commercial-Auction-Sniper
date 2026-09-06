import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.symonds_sampson import _event_links, _is_target, _property_links, _parse_date, _image


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

    def test_commercial_and_mixed_use_are_kept_but_plain_house_is_rejected(self):
        self.assertTrue(_is_target("Grade II Listed public house with living accommodation upstairs and redevelopment potential"))
        self.assertTrue(_is_target("Mixed use retail and residential investment property"))
        self.assertTrue(_is_target("Commercial office building with parking"))
        self.assertTrue(_is_target("Development site with planning permission"))
        self.assertFalse(_is_target("Detached house with four bedrooms and garden requiring modernisation"))
        self.assertFalse(_is_target("Three bedroom flat for sale by auction"))


if __name__ == "__main__":
    unittest.main()
