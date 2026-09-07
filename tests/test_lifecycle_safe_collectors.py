import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup

from collectors.core import Lot
from collectors import auction_house_london_resilient as ahl
from collectors import clive_emson_resilient as clive


class AuctionHouseLondonLifecycleTests(unittest.TestCase):
    def test_sold_prior_commercial_lot_is_retained_with_terminal_status(self):
        index = BeautifulSoup('''
        <html><body>
          <h1>30th September 2026</h1>
          <article>
            <div>LOT 12 Sold Prior Retail Property 1 High Street, London SW1A 1AA</div>
            <a href="/lot/retail-property-12">View lot</a>
          </article>
        </body></html>
        ''', 'lxml')

        def fake_detail(source, url, seed='', lot_number=None, auction_date=None, **kwargs):
            self.assertFalse(kwargs.get('suppress_prior', True))
            return Lot(
                source=source, url=url, address='1 High Street, London SW1A 1AA',
                lot_number=lot_number, auction_date=auction_date,
                guide_price=200000, property_type='Retail',
                description='Sold Prior Retail Property',
            ).finalise()

        with patch.object(ahl, 'soup', return_value=index), patch.object(ahl, 'detail_lot', side_effect=fake_detail):
            lots, dates, failures, expected = ahl._collect_page(ahl.CURRENT)

        self.assertEqual(failures, 0)
        self.assertEqual(expected, 1)
        self.assertEqual(len(lots), 1)
        self.assertEqual(lots[0].status, 'SOLD PRIOR')


class CliveEmsonLifecycleTests(unittest.TestCase):
    def test_terminal_detail_is_parsed_not_discarded(self):
        page = BeautifulSoup('''
        <html><body>
          <h1>Lot 29</h1>
          <h2>1 Market Street, Truro, Cornwall TR1 1AA</h2>
          <div>Sold Prior</div>
          <div>Category Commercial</div>
          <div>Tenure Freehold</div>
          <div>Guide Price £180,000</div>
          <div>Auction Date: 24th September 2026</div>
        </body></html>
        ''', 'lxml')
        with patch.object(clive, 'soup', return_value=page):
            lot = clive._parse_detail('https://www.cliveemson.co.uk/properties/999/29/', 'LOT 29 Commercial', '2026-09-24')
        self.assertIsNotNone(lot)
        self.assertEqual(lot.status, 'SOLD PRIOR')
        self.assertEqual(lot.tenure, 'Freehold')
        self.assertEqual(lot.guide_price, 180000)


if __name__ == '__main__':
    unittest.main()
