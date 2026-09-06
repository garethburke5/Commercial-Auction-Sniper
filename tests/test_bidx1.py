import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.bidx1 import _commercial_card, _date_from_card, _discover, _image_from_detail


class BidX1CollectorTests(unittest.TestCase):
    def test_commercial_card_rejects_plain_residential(self):
        self.assertTrue(_commercial_card("Bidding Opens 17/09 11:00 Former Shop Guide Price £100,000 Commercial Auction"))
        self.assertTrue(_commercial_card("Bidding Opens 17/09 11:00 Mixed Use freehold investment"))
        self.assertFalse(_commercial_card("Bidding Opens 17/09 11:00 Two bedroom flat Residential Auction"))

    def test_card_date_without_year_is_inferred(self):
        self.assertEqual(_date_from_card("Bidding Opens 17/09 11:00", today=date(2026, 9, 6)), "2026-09-17")
        self.assertEqual(_date_from_card("Auction Date 10 September", today=date(2026, 9, 6)), "2026-09-10")

    def test_discovery_paginates_and_deduplicates(self):
        pages = {
            "https://bidx1.com/en/united-kingdom": """
                <html><body>
                  <a href='/en/en-gb/auction/property/108626'>Bidding Opens 17/09 11:00 311-314 Whapload Road Guide Price £695,000 Commercial Auction</a>
                  <a href='/en/en-gb/auction/property/100001'>Bidding Opens 17/09 11:00 Flat 1 Example Road Guide Price £150,000 Residential Auction</a>
                </body></html>
            """,
            "https://bidx1.com/en/united-kingdom?page=2": """
                <html><body>
                  <a href='/en/en-gb/auction/property/108045'>Bidding Opens 17/09 11:00 Former Bulls Cottages Site Guide Price £50,000 Commercial Auction</a>
                </body></html>
            """,
            "https://bidx1.com/en/united-kingdom?page=3": "<html><body>No lots</body></html>",
        }

        def fetcher(url):
            return BeautifulSoup(pages[url], "lxml")

        targets, dates, pages_read, complete = _discover(fetcher=fetcher, today=date(2026, 9, 6))
        self.assertTrue(complete)
        self.assertEqual(pages_read, 3)
        self.assertEqual(len(targets), 2)
        self.assertEqual(dates, ("2026-09-17",))
        self.assertIn("https://bidx1.com/en/en-gb/auction/property/108626", targets)
        self.assertIn("https://bidx1.com/en/en-gb/auction/property/108045", targets)

    def test_image_selector_ignores_agents_and_support(self):
        s = BeautifulSoup("""
            <html><body>
              <img src='https://images-prd.bidx1.com/support/person.jpg' alt='BidX1 Support'>
              <img src='https://images-prd.bidx1.com/properties/108626/front.jpg' alt='Property'>
              <img src='https://images-prd.bidx1.com/agent/simon.jpg' alt='Agent'>
            </body></html>
        """, "lxml")
        self.assertEqual(
            _image_from_detail(s, "https://bidx1.com/en/en-gb/auction/property/108626"),
            "https://images-prd.bidx1.com/properties/108626/front.jpg",
        )


if __name__ == "__main__":
    unittest.main()
