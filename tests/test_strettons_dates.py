import unittest
from collectors.strettons import _parse_detail_auction_date


class StrettonsDateTests(unittest.TestCase):
    def test_rescheduled_date_outranks_old_catalogue_date(self):
        text = (
            "10 Sep 26 - Lot 25 LONG LEASEHOLD RESIDENTIAL INVESTMENT. "
            "Guide Price TO BE OFFERED IN OUR 29TH OCTOBER AUCTION"
        )
        self.assertEqual(_parse_detail_auction_date(text, "2026-09-10"), "2026-10-29")

    def test_normal_lot_page_date_is_retained(self):
        text = "Guide Price £185,000 PLUS Thu Sep 10 2026 11:00am To be auctioned in 3 Days"
        self.assertEqual(_parse_detail_auction_date(text, "2026-09-10"), "2026-09-10")


if __name__ == "__main__":
    unittest.main()
