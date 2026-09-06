import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import (
    _auction_date, _is_target, _lot_links, _property_type, _image,
    _terminal_status_near_title,
)


class AuctionEstatesCollectorTests(unittest.TestCase):
    def test_next_auction_date_parser(self):
        self.assertEqual(_auction_date("Next auction Thursday 8th October 2026 2.30PM"), "2026-10-08")

    def test_catalogue_link_discovery_ignores_non_property_links(self):
        s = BeautifulSoup("""
        <html><body>
          <div><a href='/property/eldon-chambers-nottingham-363629'>View Property</a><p>Guide price £225,000+</p></div>
          <div><a href='/property/26-bluecoat-close-nottingham-364585'>View Property</a><p>Guide price £125,000+</p></div>
          <a href='/next-auction'>Next auction</a>
        </body></html>
        """, "lxml")
        found = _lot_links(s)
        self.assertEqual(len(found), 2)

    def test_image_recovers_lazy_gallery_image_and_rejects_logo(self):
        s = BeautifulSoup('''
        <html><head><meta property="og:image" content="/images/logo.png"></head><body>
          <img src="/assets/logo.svg" alt="Auction Estates" />
          <img data-src="https://media.auctionestates.co.uk/property/363629/hero-main.jpg" alt="Property photograph" />
        </body></html>
        ''', "lxml")
        self.assertEqual(
            _image(s, "https://www.auctionestates.co.uk/property/eldon-chambers-nottingham-363629"),
            "https://media.auctionestates.co.uk/property/363629/hero-main.jpg",
        )

    def test_property_type_parser_and_commercial_filter(self):
        commercial = "Guide price £225,000 Property Type Commercial Key Features freehold five-storey restaurant"
        mixed = "Property Type Mixed Use Key Features shop with flat above"
        investment = "Property Type Investment Key Features commercial investment property let to Bosk Bar"
        residential = "Property Type Residential Bedrooms 3 Bathrooms 1 Key Features freehold three-bedroom house"
        self.assertEqual(_property_type(commercial), "Commercial")
        self.assertTrue(_is_target(commercial))
        self.assertTrue(_is_target(mixed))
        self.assertTrue(_is_target(investment))
        self.assertFalse(_is_target(residential))

    def test_terminal_status_is_read_from_current_lot_header(self):
        s = BeautifulSoup('''
        <html><body>
          <h1>62 Station Street, Kirkby-in-Ashfield, NG17 7AS</h1>
          <div class="status">SoldPrior</div>
          <div>Guide price £80,000+</div>
          <div>Property Type Commercial</div>
        </body></html>
        ''', "lxml")
        self.assertEqual(_terminal_status_near_title(s), "SOLD PRIOR")

    def test_other_lot_sold_prior_badge_does_not_suppress_live_lot(self):
        s = BeautifulSoup('''
        <html><body>
          <h1>Live Commercial Lot, Nottingham, NG1 1AA</h1>
          <div>Guide price £200,000+</div>
          <div>Property Type Commercial</div>
          <section class="other-properties">
            <h2>Other properties</h2><div>62 Station Street SoldPrior</div>
          </section>
        </body></html>
        ''', "lxml")
        self.assertIsNone(_terminal_status_near_title(s))


if __name__ == "__main__":
    unittest.main()
