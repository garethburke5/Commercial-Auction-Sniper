import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import _detail


class ReportedFalsePositiveRegressionTests(unittest.TestCase):
    def _fetcher(self, html):
        return lambda _url: BeautifulSoup(html, "lxml")

    def test_new_alexandra_court_residential_ast_is_not_promoted_by_commercial_footer(self):
        html = '''
        <html><body>
          <h1>Apartment 63 The New Alexandra Court, Woodborough Road, Nottingham, NG3 4LN</h1>
          <div>Guide price £39,000+</div>
          <div>Property Type Residential</div>
          <div>Reception Rooms 1 Bedrooms 1 Bathrooms 1</div>
          <h3>Key Features</h3>
          <p>Long Leasehold one-bedroom apartment let on an AST at £7,590 per annum. Investment opportunity.</p>
          <footer>Commercial Lots | Shops | Offices | Investment Property</footer>
        </body></html>
        '''
        lot = _detail(
            "https://www.auctionestates.co.uk/property/apartment-63-the-new-alexandra-court-999999",
            "Guide £39,000 investment",
            "2026-10-08",
            fetcher=self._fetcher(html),
        )
        self.assertIsNone(lot)

    def test_noel_street_six_bed_house_is_not_promoted_by_refurbishment_or_footer(self):
        html = '''
        <html><body>
          <h1>96 Noel Street, Nottingham, NG7 6AU</h1>
          <div>Guide price £195,000+</div>
          <div>Property Type Residential</div>
          <div>Reception Rooms 2 Bedrooms 6 Bathrooms 2</div>
          <h3>Key Features</h3>
          <p>Freehold six-bedroom semi-detached house. Cosmetic kitchen refurbishment. Suitable to owner occupiers and investors.</p>
          <footer>Commercial Lots | Retail Shops | Offices | Development Opportunities</footer>
        </body></html>
        '''
        lot = _detail(
            "https://www.auctionestates.co.uk/property/96-noel-street-nottingham-999998",
            "Guide £195,000 refurbishment investment",
            "2026-10-08",
            fetcher=self._fetcher(html),
        )
        self.assertIsNone(lot)

    def test_explicit_mixed_use_still_survives_footer_noise(self):
        html = '''
        <html><body>
          <h1>10 High Street, Nottingham, NG1 1AA</h1>
          <div>Guide price £200,000+</div>
          <div>Property Type Mixed Use</div>
          <div>Reception Rooms 0 Bedrooms 2 Bathrooms 1</div>
          <h3>Key Features</h3>
          <p>Freehold ground floor shop with two-bedroom flat above producing £18,000 per annum.</p>
          <footer>Residential Lots | Houses | Flats</footer>
        </body></html>
        '''
        lot = _detail(
            "https://www.auctionestates.co.uk/property/10-high-street-nottingham-999997",
            "Guide £200,000",
            "2026-10-08",
            fetcher=self._fetcher(html),
        )
        self.assertIsNotNone(lot)
        self.assertEqual(lot.property_type, "Mixed Use")


if __name__ == "__main__":
    unittest.main()
