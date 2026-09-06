import unittest
from bs4 import BeautifulSoup

from collectors.pattinson import (
    BASE,
    PARTNER_BASE,
    PARTNER_SEARCH,
    RIGHTMOVE_SEARCH,
    SEARCH,
    _auction_card,
    _canonical_property_url,
    _discover_with,
    _is_closed,
    _lot_from_card,
    _page_url,
    _parse_rightmove_page,
    _parse_search_html,
    _partner_property_url,
    _property_id,
)


class PattinsonCollectorTests(unittest.TestCase):
    def test_search_is_auction_first_and_partner_is_first_party(self):
        self.assertEqual(SEARCH, "https://www.pattinson.co.uk/auction/property-search")
        self.assertEqual(PARTNER_SEARCH, "https://addisonbarton.pattinson.co.uk/")
        self.assertIn("BRANCH%5E251528", RIGHTMOVE_SEARCH)
        self.assertIn("p=2", _page_url(2))
        self.assertIn("IncludeCommercialProperties=true", _page_url(2))
        self.assertIn("OnlineOnly=true", _page_url(2))
        self.assertIn("PageSize=100", _page_url(2))

    def test_partner_and_main_property_links_share_one_canonical_identity(self):
        self.assertEqual(_property_id("/property/512345"), "512345")
        self.assertEqual(_property_id("https://www.pattinson.co.uk/property/512345?x=1"), "512345")
        self.assertEqual(_property_id("https://addisonbarton.pattinson.co.uk/property?id=512345"), "512345")
        self.assertEqual(_canonical_property_url("https://addisonbarton.pattinson.co.uk/property?id=512345"), f"{BASE}/property/512345")
        self.assertEqual(_partner_property_url("https://www.pattinson.co.uk/property/512345"), f"{PARTNER_BASE}/property?id=512345")

    def test_commercial_auction_card_is_accepted(self):
        card = "Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, Lancashire, FY3 9DA Allocated parking"
        self.assertTrue(_auction_card(card))

    def test_mixed_use_marker_overrides_residential_wording(self):
        card = "Starting Bid£180,000 Mixed Use shop and flat with two bedroom apartment above, High Street, NE1 1AA"
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

    def test_sold_via_auction_marketing_is_not_terminal_status(self):
        self.assertFalse(_is_closed("Being Sold Via Online Auction. Fees Apply."))
        self.assertFalse(_is_closed("Property sold by online auction method; bidding is open."))
        self.assertTrue(_is_closed("SOLD STC - online auction property"))
        self.assertTrue(_is_closed("SOLD Starting Bid £60,000"))

    def test_withdrawn_commercial_auction_card_is_rejected(self):
        card = "Withdrawn Starting Bid£60,000 Commercial Development in TS18 High Street, Stockton, Durham, TS18 1PL"
        self.assertFalse(_auction_card(card))

    def test_html_parser_keeps_only_current_auction_commercial_and_handles_partner_links(self):
        html = """
        <html><body><h1>1780 results</h1>
        <a href="/property/512345">Starting Bid£60,000 Commercial Development in TS18 High Street, Stockton, Durham, TS18 1PL On Street parking</a>
        <a href="/property?id=512346">Starting Bid£90,000 Retail in NE1 High Street, Newcastle, NE1 1AA</a>
        <a href="/property/512347">£12,600 Industrial in NE63 Alexandra Enterprise Centre, Ashington, NE63 8UB Allocated parking</a>
        <a href="/property/512348">SOLD Starting Bid£90,000 Retail in NE1 High Street, Newcastle, NE1 1AA</a>
        <a href="/?p=89">89</a>
        </body></html>
        """
        found, total, ids, max_page = _parse_search_html(html)
        self.assertEqual(total, 1780)
        self.assertEqual(set(found), {
            "https://www.pattinson.co.uk/property/512345",
            "https://www.pattinson.co.uk/property/512346",
        })
        self.assertEqual(ids, {"512345", "512346", "512347", "512348"})
        self.assertEqual(max_page, 89)

    def test_rightmove_fallback_reads_count_card_address_and_image(self):
        html = """
        <html><body><script>window.__DATA__={"resultCount":"2"};</script>
          <div class="property-card">
            <a href="/properties/90936798#/?channel=COM_BUY"><img src="https://media.rightmove.co.uk/1.jpg"/></a>
            <a href="/properties/90936798#/?channel=COM_BUY">£1,680,000 Guide Price</a>
            <a href="/properties/90936798#/?channel=COM_BUY">Long Lane, Bickerstaffe, Ormskirk, Lancashire, L39 9EE Commercial Development</a>
            <a href="/properties/90936798#/?channel=COM_BUY">Being Sold Via Online Auction. Fees Apply. A rare mixed use commercial and residential opportunity.</a>
          </div>
          <div class="property-card">
            <a href="/properties/2#/?channel=COM_BUY">£200,000 Guide Price</a>
            <a href="/properties/2#/?channel=COM_BUY">Somewhere Road, London, SW1A 1AA Office</a>
            <a href="/properties/2#/?channel=COM_BUY">Normal private treaty sale.</a>
          </div>
        </body></html>
        """
        found, total, ids = _parse_rightmove_page(BeautifulSoup(html, "lxml"))
        self.assertEqual(total, 2)
        self.assertEqual(ids, {"90936798", "2"})
        self.assertEqual(len(found), 1)
        lot = next(iter(found.values()))
        self.assertEqual(lot.address, "Long Lane, Bickerstaffe, Ormskirk, Lancashire, L39 9EE")
        self.assertEqual(lot.guide_price, 1680000.0)
        self.assertEqual(lot.property_type, "Commercial Development")
        self.assertEqual(lot.image_url, "https://media.rightmove.co.uk/1.jpg")

    def test_rightmove_closed_or_sstc_card_is_rejected_even_on_auction_branch(self):
        html = """
        <html><body><script>{"resultCount":"1"}</script><div>
          <a href="/properties/99#/?channel=COM_BUY">£90,000 Guide Price</a>
          <a href="/properties/99#/?channel=COM_BUY">High Street, Redcar, TS10 1AA Retail Property (high street)</a>
          <a href="/properties/99#/?channel=COM_BUY">SOLD STC - for sale via online auction.</a>
        </div></body></html>
        """
        found, total, ids = _parse_rightmove_page(BeautifulSoup(html, "lxml"))
        self.assertEqual(total, 1)
        self.assertEqual(ids, {"99"})
        self.assertEqual(found, {})

    def test_card_address_does_not_keep_outcode_prefix(self):
        card = "Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, Lancashire, FY3 9DA Allocated parking"
        lot = _lot_from_card(card, "https://www.pattinson.co.uk/property/512345")
        self.assertIsNotNone(lot)
        self.assertEqual(lot.address, "Whitegate Drive, Blackpool, Lancashire, FY3 9DA")
        self.assertEqual(lot.guide_price, 110000.0)

    def test_residential_only_page_does_not_end_full_auction_sweep(self):
        pages = {
            1: """<html><body><h1>60 results</h1><a href='/property/1'>Starting Bid£50,000 2 bed flat in Somewhere</a><a href='/?p=3'>3</a></body></html>""",
            2: """<html><body><a href='/property/2'>Starting Bid£75,000 3 bed house in Elsewhere</a></body></html>""",
            3: """<html><body><a href='/property/3'>Starting Bid£90,000 Retail in NE1 High Street, Newcastle, NE1 1AA</a></body></html>""",
        }

        def fetcher(url):
            from urllib.parse import parse_qs, urlparse
            page = int((parse_qs(urlparse(url).query).get("p") or ["1"])[0])
            return BeautifulSoup(pages.get(page, "<html><body></body></html>"), "lxml")

        found, total, pages_seen = _discover_with(fetcher)
        self.assertEqual(total, 60)
        self.assertEqual(pages_seen, 4)
        self.assertIn("https://www.pattinson.co.uk/property/3", found)

    def test_duplicate_page_ids_stop_a_broken_pagination_loop(self):
        page = BeautifulSoup("""<html><body><h1>100 results</h1><a href='/property/10'>Starting Bid£90,000 Retail in NE1 High Street, Newcastle, NE1 1AA</a><a href='/?p=50'>50</a></body></html>""", "lxml")
        calls = []

        def fetcher(url):
            calls.append(url)
            return page

        found, total, pages_seen = _discover_with(fetcher)
        self.assertEqual(total, 100)
        self.assertEqual(len(found), 1)
        self.assertEqual(pages_seen, 2)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
