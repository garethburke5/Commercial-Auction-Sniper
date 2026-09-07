import unittest
from datetime import date

from collectors import acuitus_resilient as acuitus


class AcuitusDynamicTests(unittest.TestCase):
    def test_current_auction_date_is_derived_from_homepage_copy(self):
        text = (
            "Current Auction Live streamed: Thursday 17 September 2026 at 1pm. "
            "Entries now invited: Thursday 29 October 2026 Thursday 10 December 2026"
        )
        self.assertEqual(
            acuitus._parse_current_auction_date(text, today=date(2026, 9, 7)),
            date(2026, 9, 17),
        )

    def test_card_must_belong_to_current_auction(self):
        current = date(2026, 9, 17)
        self.assertTrue(acuitus._card_matches_date("Auction 17/09/2026 Retail Investment", current))
        self.assertTrue(acuitus._card_matches_date("17th September 2026 Office Investment", current))
        self.assertFalse(acuitus._card_matches_date("Other Available Properties Private Sale Retail Investment", current))
        self.assertFalse(acuitus._card_matches_date("Auction 29 October 2026 Retail Investment", current))

    def test_terminal_status_is_history_evidence(self):
        self.assertEqual(acuitus._terminal_status("Sold Prior"), "SOLD PRIOR")
        self.assertEqual(acuitus._terminal_status("Withdrawn Prior"), "WITHDRAWN")
        self.assertEqual(acuitus._terminal_status("Postponed"), "POSTPONED")


if __name__ == "__main__":
    unittest.main()
