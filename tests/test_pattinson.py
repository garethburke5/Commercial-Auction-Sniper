import unittest

from collectors.pattinson import _auction_card, _parse_search_markdown, _lot_from_card


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

    def test_reader_markdown_recovers_exact_property_urls_and_total(self):
        markdown = """
        ##### 422 results
        [Starting Bid£60,000 Commercial Development in TS18 High Street, Stockton, Durham, TS18 1PL On Street parking](https://www.pattinson.co.uk/property/512345)
        [Starting Bid£275,000 Residential Development in NN1 St. Michaels Avenue, Northampton, NN1 4JQ Allocated parking](https://www.pattinson.co.uk/property/512346)
        [£12,600 Industrial in NE63 Alexandra Enterprise Centre, Ashington, NE63 8UB Allocated parking](https://www.pattinson.co.uk/property/512347)
        """
        found, total = _parse_search_markdown(markdown)
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
