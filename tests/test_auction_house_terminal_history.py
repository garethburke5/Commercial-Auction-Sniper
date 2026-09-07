import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from collectors.core import Lot
from collectors import auction_house_regions_resilient as resilient


class AuctionHouseTerminalHistoryTests(unittest.TestCase):
    def test_terminal_status_parser(self):
        self.assertEqual(resilient._terminal_status("Lot - Sold Prior Commercial Property"), "SOLD PRIOR")
        self.assertEqual(resilient._terminal_status("Withdrawn Office"), "WITHDRAWN")
        self.assertEqual(resilient._terminal_status("POSTPONED Mixed Use"), "POSTPONED")
        self.assertIsNone(resilient._terminal_status("Guide £225,000 Commercial Property"))

    def test_explicit_and_ambiguous_auction_house_categories(self):
        self.assertTrue(resilient._is_target_card("Lot 8 Hospitality Oakbank, Church Stretton SY6 6AQ"))
        self.assertTrue(resilient._is_target_card("Lot 9 Heavy Industrial Bispham Facility FY2 0JF"))
        self.assertFalse(resilient._is_target_card("Lot 10 Terraced House 4 Wentbridge Road BL1 2QR"))
        self.assertTrue(resilient._is_ambiguous_card("Property For Sale Robinwood Former School, Todmorden OL14 8HJ"))
        self.assertTrue(resilient._is_ambiguous_card("Land For Sale Plot at High Street AB1 2CD"))

    def test_current_sale_terminal_and_generic_commercial_assets_are_preserved(self):
        event_html = '''
        <html><body>
          <article>
            <div>Lot 1 - Sold Prior Commercial Property 340 Upton Road, Upton, Prenton, CH43 9RW</div>
            <a href="/northwest/auction/lot/150542">View lot</a>
          </article>
          <article>
            <div>Lot 2 - Guide £375,000 Hospitality Oakbank, Cunnery Road, Church Stretton, SY6 6AQ</div>
            <a href="/northwest/auction/lot/152198">View lot</a>
          </article>
          <article>
            <div>Lot 3 - Guide £90,000 Terraced House 4 Wentbridge Road, Bolton, BL1 2QR</div>
            <a href="/northwest/auction/lot/152166">View lot</a>
          </article>
          <article>
            <div>Guide £370,000 Property For Sale Robinwood Former School, Jumps Road, Todmorden, OL14 8HJ</div>
            <a href="/northwest/auction/lot/151281">View lot</a>
          </article>
        </body></html>
        '''
        page = BeautifulSoup(event_html, "lxml")

        def fake_detail(source, url, seed="", lot_number=None, auction_date=None, **kwargs):
            if url.endswith("150542"):
                self.assertTrue(kwargs.get("force_commercial"))
                return Lot(
                    source=source, url=url,
                    address="340 Upton Road, Upton, Birkenhead, Prenton, Merseyside CH43 9RW",
                    lot_number=lot_number, auction_date=auction_date,
                    tenure="Freehold", property_type="Commercial Property",
                    description="Sold Prior Commercial Property Tenure Freehold",
                ).finalise()
            if url.endswith("152198"):
                self.assertTrue(kwargs.get("force_commercial"))
                return Lot(
                    source=source, url=url,
                    address="Oakbank, Cunnery Road, Church Stretton, Shropshire SY6 6AQ",
                    lot_number=lot_number, auction_date=auction_date,
                    guide_price=375000, tenure="Freehold", property_type="Hospitality",
                    description="Hospitality property offered for sale by auction",
                ).finalise()
            if url.endswith("151281"):
                self.assertFalse(kwargs.get("force_commercial"))
                return Lot(
                    source=source, url=url,
                    address="Robinwood Former School, Jumps Road, Todmorden, West Yorkshire OL14 8HJ",
                    lot_number=lot_number, auction_date=auction_date,
                    guide_price=370000, tenure="Freehold", property_type="Commercial Development",
                    description="Former school activity centre. Commercial Development. Business Rates £22,400.",
                ).finalise()
            raise AssertionError("Residential lot should never be hydrated")

        with patch.object(
            resilient.base, "_future_events",
            return_value={"https://www.auctionhouse.co.uk/northwest/auction/2026/09/16": "2026-09-16"},
        ), patch.object(resilient.base, "_fetch", return_value=page), patch.object(
            resilient, "detail_lot", side_effect=fake_detail
        ):
            result = resilient._collect_region("northwest")

        self.assertEqual(result.status, "LIVE")
        self.assertEqual(result.expected_count, 3)
        self.assertTrue(result.authoritative_snapshot)
        by_url = {lot.url: lot for lot in result.lots}
        self.assertEqual(by_url["https://www.auctionhouse.co.uk/northwest/auction/lot/150542"].status, "SOLD PRIOR")
        self.assertEqual(by_url["https://www.auctionhouse.co.uk/northwest/auction/lot/152198"].status, "CURRENT")
        self.assertEqual(by_url["https://www.auctionhouse.co.uk/northwest/auction/lot/151281"].property_type, "Commercial Development")
        self.assertNotIn("https://www.auctionhouse.co.uk/northwest/auction/lot/152166", by_url)


if __name__ == "__main__":
    unittest.main()
