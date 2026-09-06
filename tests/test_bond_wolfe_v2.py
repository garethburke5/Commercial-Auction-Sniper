import unittest
from bs4 import BeautifulSoup

from collectors.bond_wolfe_v2 import _available_commercial_order_card, _order_targets


class BondWolfeV2Tests(unittest.TestCase):
    def test_available_order_card_requires_commercial_or_mixed_and_excludes_prior(self):
        self.assertTrue(_available_commercial_order_card("Lot 3 Commercial Vacant Land/Development"))
        self.assertTrue(_available_commercial_order_card("Lot 25 Mixed Use"))
        self.assertFalse(_available_commercial_order_card("Lot 4 Land/Development"))
        self.assertFalse(_available_commercial_order_card("Lot 183 Commercial Investment Sold Prior"))
        self.assertFalse(_available_commercial_order_card("Lot 184 Mixed Use Withdrawn"))

    def test_order_targets_uses_full_order_and_filters_unavailable_rows(self):
        html = '''
        <main>
          <a href="/auctions/properties/100-property-auction-birmingham/">Lot 3 Commercial Vacant Land/Development View lot</a>
          <a href="/auctions/properties/101-property-auction-birmingham/">Lot 4 Land/Development View lot</a>
          <a href="/auctions/properties/102-property-auction-birmingham/">Lot 25 Mixed Use View lot</a>
          <a href="/auctions/properties/103-property-auction-birmingham/">Lot 183 Commercial Investment Sold Prior View lot</a>
          <a href="/auctions/properties/102-property-auction-birmingham/">Lot 25 Mixed Use View lot</a>
        </main>
        '''
        targets = _order_targets(BeautifulSoup(html, "lxml"))
        self.assertEqual(len(targets), 2)
        self.assertEqual([x[2] for x in targets], ["Lot 3", "Lot 25"])
        self.assertTrue(targets[0][0].endswith("100-property-auction-birmingham/"))
        self.assertTrue(targets[1][0].endswith("102-property-auction-birmingham/"))


if __name__ == "__main__":
    unittest.main()
