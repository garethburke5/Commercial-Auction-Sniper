import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import (
    _auction_date, _is_target, _lot_links, _property_type, _image,
    _terminal_status_near_title, _tenancy_details, _detail,
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

    def test_exact_residential_tavistock_flat_is_rejected(self):
        html = '''
        <html><body>
          <h1>36 Tavistock Court, Nottingham, NG5 2EH</h1>
          <div>Guide price £30,000+</div>
          <div>Property Type Residential</div>
          <div>Reception Rooms 1 Bedrooms 1 Bathrooms 1</div>
          <h3>Key Features</h3>
          <p>An opportunity to acquire a one-bedroom apartment let on an AST at £6,540 pa.</p>
          <p>Long Leasehold one-bedroom apartment. Ideal for investors.</p>
        </body></html>
        '''
        fetcher = lambda url: BeautifulSoup(html, "lxml")
        self.assertIsNone(_detail(
            "https://www.auctionestates.co.uk/property/36-tavistock-court-nottingham-ng5-2eh-364189",
            "36 Tavistock Court Guide price £30,000+",
            "2026-10-08",
            fetcher=fetcher,
        ))

    def test_exact_residential_bluecoat_house_is_rejected(self):
        html = '''
        <html><body>
          <h1>26 Bluecoat Close, Nottingham, NG1 4DP</h1>
          <div>Guide price £125,000+</div>
          <div>Property Type Residential</div>
          <div>Bedrooms 3 Bathrooms 1</div>
          <h3>Key Features</h3>
          <p>A well presented 3 bedroom house with garage and allocated parking space.</p>
          <p>Freehold, offered with full vacant possession.</p>
        </body></html>
        '''
        fetcher = lambda url: BeautifulSoup(html, "lxml")
        self.assertIsNone(_detail(
            "https://www.auctionestates.co.uk/property/26-bluecoat-close-nottingham-ng1-4dp-364585",
            "26 Bluecoat Close Guide price £125,000+",
            "2026-10-08",
            fetcher=fetcher,
        ))

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

    def test_postponed_guide_status_is_archived_not_live(self):
        s = BeautifulSoup('''
        <html><body>
          <h1>Commercial Lot, Nottingham, NG1 1AA</h1>
          <div>Guide price</div><div>POSTPONED</div>
          <div>Property Type Commercial</div>
          <h3>Key Features</h3>
          <div>Unrelated other property SoldPrior</div>
        </body></html>
        ''', "lxml")
        self.assertEqual(_terminal_status_near_title(s), "POSTPONED")

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

    def test_extracts_named_tenant_term_and_start_from_current_lease(self):
        text = (
            "An opportunity to acquire a retail investment property let to D & D Security Midland Limited "
            "located in the heart of Ilkeston town centre. Current Rent Reserved of £9,999.96 pa. "
            "The property is let on a 9 year lease from 14th April 2017."
        )
        tenant, term, start, fri, break_clause = _tenancy_details(text)
        self.assertEqual(tenant, "D & D Security Midland Limited")
        self.assertEqual(term, "9 years")
        self.assertEqual(start, "14 April 2017")
        self.assertIsNone(fri)
        self.assertIsNone(break_clause)

    def test_extracts_explicit_fri_term_and_no_break_without_inventing_tenant(self):
        text = "The unit is occupied under a 10 year FRI lease. There is no break clause. Nearby occupiers: Tesco, Boots."
        tenant, term, start, fri, break_clause = _tenancy_details(text)
        self.assertIsNone(tenant)
        self.assertEqual(term, "10 years")
        self.assertIsNone(start)
        self.assertTrue(fri)
        self.assertEqual(break_clause, "No break")


if __name__ == "__main__":
    unittest.main()
