import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.allsop import (
    _card_is_target,
    _extract_targets,
    _address_from_soup,
    _header_auction_date,
    _live_status_probe,
    _page_auction_dates,
    _date_for_card,
    _teaser_address,
    _teaser_lot,
)


class AllsopCollectorTests(unittest.TestCase):
    def test_current_landing_card_without_hyphen_is_commercial(self):
        card = "Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Substantial Freehold Retail Investment Guide Price £5.8M"
        self.assertTrue(_card_is_target(card))

    def test_extracts_lot_overview_from_canonical_landing_markup(self):
        html = '''
        <section><p>Next commercial auction 7th October 2026</p>
          <article>
            <div>Commercial LOT - Oct 2026</div><div>FEATURED LOT</div>
            <h3>Sheffield S10</h3>
            <p>Substantial Freehold Retail, Supermarket &amp; Car Park Investment</p>
            <img src="/media/auction/lot-44.jpg" alt="Sheffield investment" />
            <a href="/lot-overview/substantial-freehold-retail-supermarket-car-park-investment-in-sheffield/c261001-044">View lot</a>
          </article>
        </section>
        '''
        found = {}
        _extract_targets(BeautifulSoup(html, "lxml"), found)
        self.assertEqual(len(found), 1)
        url = next(iter(found))
        self.assertIn("/lot-overview/", url)
        self.assertIn("Commercial LOT - Oct 2026", found[url]["card"])
        self.assertEqual(found[url]["image"], "https://www.allsop.co.uk/media/auction/lot-44.jpg")
        self.assertEqual(found[url]["auction_date"], "2026-10-07")

    def test_rejects_pure_residential_card(self):
        self.assertFalse(_card_is_target("Residential LOT 12 - Sep 2026 Two Bedroom Flat London SW1"))

    def test_address_uses_direct_text_node_not_large_parent(self):
        html = '''
        <main>
          <div><h2>LOT 66 - London</h2><p>7 Kenway Road, Earls Court, London, SW5 0RP</p></div>
          <section>{}</section>
        </main>
        '''.format("boilerplate " * 300)
        s = BeautifulSoup(html, "lxml")
        self.assertEqual(_address_from_soup(s, ""), "7 Kenway Road, Earls Court, London, SW5 0RP")

    def test_catalogue_header_date_is_parsed(self):
        self.assertEqual(_header_auction_date("Residential - 16th & 17th Sept 2026 - Live Stream"), "2026-09-16")

    def test_page_dates_match_month_only_teaser_to_real_auction_day(self):
        s = BeautifulSoup('''
        <main>
          <p>Future Auction Dates</p>
          <p>Wednesday 7th October 2026</p>
          <p>Wednesday 11th November 2026</p>
        </main>
        ''', "lxml")
        dates = _page_auction_dates(s, today=date(2026, 9, 6))
        self.assertEqual(dates, ("2026-10-07", "2026-11-11"))
        self.assertEqual(_date_for_card("Commercial LOT - Oct 2026", dates), "2026-10-07")
        self.assertEqual(_date_for_card("Commercial LOT - Nov 2026", dates), "2026-11-11")

    def test_generic_page_chrome_sold_prior_does_not_enter_status_probe(self):
        s = BeautifulSoup('''<main><h1>INVESTMENT - Freehold Mixed Use Building</h1><p>Other auction results include sold prior lots.</p></main>''', "lxml")
        probe = _live_status_probe(s, "Residential LOT 66 - Sep 2026 Mixed Use Building")
        self.assertNotIn("sold prior", probe.lower())

    def test_future_featured_teaser_uses_exact_published_auction_date(self):
        card = "Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Substantial Freehold Retail, Supermarket & Car Park Investment Guide Price £5.8M"
        self.assertEqual(_teaser_address(card), "Sheffield S10")
        lot = _teaser_lot(
            "https://www.allsop.co.uk/lot-overview/example/c261001-044",
            card,
            "https://www.allsop.co.uk/media/auction/lot-44.jpg",
            "2026-10-07",
        )
        self.assertIsNotNone(lot)
        self.assertEqual(lot.address, "Sheffield S10")
        self.assertEqual(lot.auction_date, "2026-10-07")
        self.assertIn("Retail", lot.property_type)
        self.assertEqual(lot.image_url, "https://www.allsop.co.uk/media/auction/lot-44.jpg")


if __name__ == "__main__":
    unittest.main()
