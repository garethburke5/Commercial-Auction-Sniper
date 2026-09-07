import unittest
from bs4 import BeautifulSoup

from collectors.bond_wolfe_v2 import _order_targets, _terminal_status


class BondWolfeLifecycleTests(unittest.TestCase):
    def test_terminal_status_distinguishes_sold_prior_and_withdrawn(self):
        self.assertEqual(_terminal_status('Lot 184 Mixed Use Sold prior to auction'), 'SOLD PRIOR')
        self.assertEqual(_terminal_status('Lot 22 Commercial Investment Withdrawn'), 'WITHDRAWN')
        self.assertIsNone(_terminal_status('Lot 23 Commercial Investment Available'))

    def test_order_targets_preserve_sold_prior_commercial_row(self):
        html='''<div>
          <a href="/auctions/properties/361058-property-auction-birmingham/">Lot 184 Mixed Use Sold Prior £750,000+</a>
          <a href="/auctions/properties/361059-property-auction-birmingham/">Lot 185 Commercial Investment £200,000+</a>
          <a href="/auctions/properties/361060-property-auction-birmingham/">Lot 186 Residential Vacant £150,000+</a>
        </div>'''
        targets=_order_targets(BeautifulSoup(html,'lxml'))
        self.assertEqual(len(targets),2)
        statuses={lotno:status for _href,_card,lotno,status in targets}
        self.assertEqual(statuses['Lot 184'],'SOLD PRIOR')
        self.assertIsNone(statuses['Lot 185'])


if __name__=='__main__':
    unittest.main()
