import unittest
from bs4 import BeautifulSoup

from collectors.allsop import _card_is_target, _extract_targets


class AllsopCollectorTests(unittest.TestCase):
    def test_current_landing_card_without_hyphen_is_commercial(self):
        card = "Commercial LOT - Oct 2026 FEATURED LOT Sheffield S10 Substantial Freehold Retail Investment Guide Price £5.8M"
        self.assertTrue(_card_is_target(card))

    def test_extracts_lot_overview_from_canonical_landing_markup(self):
        html = '''
        <section>
          <article>
            <div>Commercial LOT - Oct 2026</div>
            <div>FEATURED LOT</div>
            <h3>Sheffield S10</h3>
            <p>Substantial Freehold Retail, Supermarket &amp; Car Park Investment</p>
            <a href="/lot-overview/substantial-freehold-retail-supermarket-car-park-investment-in-sheffield/c261001-044">View lot</a>
          </article>
        </section>
        '''
        found = {}
        _extract_targets(BeautifulSoup(html, "lxml"), found)
        self.assertEqual(len(found), 1)
        url = next(iter(found))
        self.assertIn("/lot-overview/", url)
        self.assertIn("Commercial LOT - Oct 2026", found[url])

    def test_rejects_pure_residential_card(self):
        self.assertFalse(_card_is_target("Residential LOT 12 - Sep 2026 Two Bedroom Flat London SW1"))


if __name__ == "__main__":
    unittest.main()
