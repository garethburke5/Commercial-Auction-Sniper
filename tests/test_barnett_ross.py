import unittest
from bs4 import BeautifulSoup

from collectors.barnett_ross import _catalogue_rows, _row_status


class BarnettRossCollectorTests(unittest.TestCase):
    def test_terminal_status_parser(self):
        self.assertEqual(_row_status("4 Units 1-5 Chard Sold Prior"), "SOLD PRIOR")
        self.assertEqual(_row_status("21 23 Wilton Place Withdrawn - Refer"), "WITHDRAWN")
        self.assertEqual(_row_status("1 474 Fulham Road Guide £3,250,000+"), "CURRENT")

    def test_authoritative_table_preserves_sold_prior_and_withdrawn(self):
        html = '''<table>
          <tr><th>Lot</th><th>Address</th><th>Guide Price</th></tr>
          <tr><td>1</td><td>474-476 Fulham Road, London SW6 1BY</td><td>Guide: £3,250,000+</td></tr>
          <tr><td>4</td><td>Units 1-5, 2-6 Fore Street, Chard TA20 1PH</td><td>Sold Prior</td></tr>
          <tr><td>21</td><td>23 Wilton Place, Harrow HA1 2HJ</td><td>Withdrawn - Refer</td></tr>
        </table>'''
        rows=_catalogue_rows(BeautifulSoup(html,'lxml'),'2026-09-10')
        self.assertEqual(len(rows),3)
        by_lot={x.lot_number:x for x in rows}
        self.assertEqual(by_lot['Lot 1'].status,'CURRENT')
        self.assertEqual(by_lot['Lot 1'].guide_price,3250000.0)
        self.assertEqual(by_lot['Lot 4'].status,'SOLD PRIOR')
        self.assertEqual(by_lot['Lot 21'].status,'WITHDRAWN')
        self.assertEqual(by_lot['Lot 4'].auction_date,'2026-09-10')


if __name__ == '__main__':
    unittest.main()
