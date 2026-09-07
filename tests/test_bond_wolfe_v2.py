import unittest
from bs4 import BeautifulSoup

from collectors.bond_wolfe_v2 import _commercial_order_card, _order_targets


class BondWolfeV2Tests(unittest.TestCase):
    def test_order_card_requires_commercial_or_mixed_but_keeps_terminal_rows(self):
        self.assertTrue(_commercial_order_card("Lot 3 Commercial Vacant Land/Development"))
        self.assertTrue(_commercial_order_card("Lot 25 Mixed Use"))
        self.assertFalse(_commercial_order_card("Lot 4 Land/Development"))
        # Availability is a lifecycle property, not a reason to erase commercial
        # market evidence from the current-sale scope.
        self.assertTrue(_commercial_order_card("Lot 183 Commercial Investment Sold Prior"))
        self.assertTrue(_commercial_order_card("Lot 184 Mixed Use Withdrawn"))

    def test_order_targets_uses_full_order_and_preserves_terminal_rows(self):
        html = '''
        <main>
          <a href="/auctions/properties/100-property-auction-birmingham/">Lot 3 Commercial Vacant Land/Development View lot</a>
          <a href="/auctions/properties/101-property-auction-birmingham/">Lot 4 Land/Development View lot</a>
          <a href="/auctions/properties/102-property-auction-birmingham/">Lot 25 Mixed Use View lot</a>
          <a href="/auctions/properties/103-property-auction-birmingham/">Lot 183 Commercial Investment Sold Prior View lot</a>
          <a href="/auctions/properties/104-property-auction-birmingham/">Lot 184 Mixed Use Withdrawn View lot</a>
          <a href="/auctions/properties/102-property-auction-birmingham/">Lot 25 Mixed Use View lot</a>
        </main>
        '''
        targets = _order_targets(BeautifulSoup(html, "lxml"))
        self.assertEqual(len(targets), 4)
        self.assertEqual([x[2] for x in targets], ["Lot 3", "Lot 25", "Lot 183", "Lot 184"])
        statuses={x[2]:x[3] for x in targets}
        self.assertIsNone(statuses["Lot 3"])
        self.assertIsNone(statuses["Lot 25"])
        self.assertEqual(statuses["Lot 183"], "SOLD PRIOR")
        self.assertEqual(statuses["Lot 184"], "WITHDRAWN")


if __name__ == "__main__":
    unittest.main()
