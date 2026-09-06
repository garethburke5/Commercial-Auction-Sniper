import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.allsop import _candidate_is_current_or_future
from collectors.harman_healy import _catalogue_candidates


class PendingCatalogueSemanticsTests(unittest.TestCase):
    def test_allsop_featured_history_tile_is_not_live_catalogue_evidence(self):
        self.assertFalse(_candidate_is_current_or_future(
            "Commercial LOT 45 - Jul 2026 FEATURED LOT Deal CT14 Freehold Care Home Investment",
            today=date(2026, 9, 6),
        ))

    def test_allsop_current_month_tile_remains_eligible(self):
        self.assertTrue(_candidate_is_current_or_future(
            "Commercial LOT 12 - Sep 2026 Manchester M2 Shop Investment",
            today=date(2026, 9, 6),
        ))

    def test_harman_announced_date_without_lot_count_is_not_published_catalogue(self):
        root = BeautifulSoup(
            "<div>Next Auction 17th September 2026</div>",
            "lxml",
        )
        cats, events = _catalogue_candidates(root)
        self.assertEqual(cats, {})
        self.assertTrue(events)

    def test_harman_positive_lot_count_enables_catalogue_probe(self):
        root = BeautifulSoup(
            "<div>Next Auction 17th September 2026 - 25 lots</div>",
            "lxml",
        )
        cats, events = _catalogue_candidates(root)
        self.assertTrue(cats)
        self.assertEqual(events[0][1], 25)


if __name__ == "__main__":
    unittest.main()
