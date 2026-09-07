import unittest

from collectors.core import parse_guide
from collectors.mchugh import _auction_date, _terminal_status


class McHughCatalogueTests(unittest.TestCase):
    def test_future_card_date_and_guide_are_parseable(self):
        card='Lot 290 | End Time - 17/09/2026 12:40 Freehold Industrial Unit Vacant Possession Guide Price*£10,000+'
        self.assertEqual(_auction_date(card),'2026-09-17')
        self.assertEqual(parse_guide(card),10000.0)

    def test_sold_prior_lifecycle_is_preserved(self):
        card='Lot 281 | Auction Ended - 26/08/2026 22:10 Result Sold Prior'
        self.assertEqual(_auction_date(card),'2026-08-26')
        self.assertEqual(_terminal_status(card),'SOLD PRIOR')

    def test_generic_auction_rules_do_not_mark_lot_terminal(self):
        self.assertIsNone(_terminal_status('Withdrawn, Postponed and Sold Prior Lots may alter scheduled end times.'))


if __name__=='__main__':
    unittest.main()
