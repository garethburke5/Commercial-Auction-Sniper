import unittest

from collectors.pattinson import _auction_card, _lot_from_card, _parse_search_html


class PattinsonCollectorTests(unittest.TestCase):
    def test_commercial_auction_card_is_accepted(self):
        card = "Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, Lancashire, FY3 9DA Allocated parking"
        self.assertTrue(_auction_card(card))

    def test_residential_development_is_rejected(self):
        card = "Starting Bid£275,000 Residential Development in NN1 St. Michaels Avenue, Northampton, NN1 4JQ Allocated parking"
        self.assertFalse(_auction_card(card))

    def test_non_auction_commercial_sale_is_rejected(self):
        card = "£12,600 Industrial in NE63 Alexandra Enterprise Centre, Ashington, NE63 8UB Allocated parking"
        self.assertFalse(_auction_card(card))

    def test_sold_commercial_auction_card_is_rejected(self):
        card = "SOLD Starting Bid£60,000 Retail in TS18 High Street, Stockton, Durham, TS18 1PL On Street parking"
        self.assertFalse(_auction_card(card))

    def test_withdrawn_commercial_auction_card_is_rejected(self):
        card = "Withdrawn Starting Bid£60,000 Commercial Development in TS18 High Street, Stockton, Durham, TS18 1PL"
        self.assertFalse(_auction_card(card))

    def test_html_parser_keeps_only_current_auction_commercial(self):
        html = """
        <html><body><h1>422 results</h1>
        <a href="/property/512345">Starting Bid£60,000 Commercial Development in TS18 High Street, Stockton, Durham, TS18 1PL On Street parking</a>
        <a href="/property/512346">Starting Bid£275,000 Residential Development in NN1 St. Michaels Avenue, Northampton, NN1 4JQ Allocated parking</a>
        <a href="/property/512347">£12,600 Industrial in NE63 Alexandra Enterprise Centre, Ashington, NE63 8UB Allocated parking</a>
        <a href="/property/512348">SOLD Starting Bid£90,000 Retail in NE1 High Street, Newcastle, NE1 1AA</a>
        </body></html>
        """
        found, total = _parse_search_html(html)
        self.assertEqual(total, 422)
        self.assertEqual(list(found), ["https://www.pattinson.co.uk/property/512345"])

    def test_card_address_does_not_keep_outcode_prefix(self):
        card = "Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, Lancashire, FY3 9DA Allocated parking"
        lot = _lot_from_card(card, "https://www.pattinson.co.uk/property/512345")
        self.assertIsNotNone(lot)
        self.assertEqual(lot.address, "Whitegate Drive, Blackpool, Lancashire, FY3 9DA")
        self.assertEqual(lot.guide_price, 110000.0)


if __name__ == "__main__":
    unittest.main()
