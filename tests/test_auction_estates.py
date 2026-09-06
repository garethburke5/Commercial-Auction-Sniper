import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import _auction_date, _is_target, _lot_links, _property_type


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


if __name__ == "__main__":
    unittest.main()
