import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup

from collectors.barnett_ross import _catalogue_rows, _row_status, _hydrate


class BarnettRossCollectorTests(unittest.TestCase):
    def test_terminal_status_parser(self):
        self.assertEqual(_row_status("4 Units 1-5 Chard Sold Prior"), "SOLD PRIOR")
        self.assertEqual(_row_status("21 23 Wilton Place Withdrawn - Refer"), "WITHDRAWN")
        self.assertEqual(_row_status("1 474 Fulham Road Guide £3,250,000+"), "CURRENT")

    def test_authoritative_table_is_reconciliation_not_commercial_classification(self):
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
        self.assertEqual(by_lot['Lot 1'].property_type,'Unclassified catalogue row')
        self.assertEqual(by_lot['Lot 4'].status,'SOLD PRIOR')
        self.assertEqual(by_lot['Lot 21'].status,'WITHDRAWN')
        self.assertEqual(by_lot['Lot 4'].auction_date,'2026-09-10')

    def test_exact_pure_residential_flat_is_rejected(self):
        html='''<main><h1>65 St Peters Close, Newbury Park, Ilford, Essex IG2 7QN</h1>
          <p>Lot 16. Vacant 2 Bed Flat. Self-Contained 2 Bed Flat on the first floor of a purpose built block.</p>
          <p>Leasehold for a term of 99 years. Offered with Vacant Possession.</p></main>'''
        with patch('collectors.barnett_ross.soup',return_value=BeautifulSoup(html,'lxml')):
            self.assertIsNone(_hydrate('https://www.barnettross.co.uk/property.php?id=1','2026-09-10'))

    def test_exact_mixed_use_investment_is_kept(self):
        html='''<main><h1>849, 849a & 849b High Road, North Finchley, London N12 8PT</h1>
          <h2>Lot 2 Commercial / Residential Investment</h2>
          <p>Ground floor retail unit with two self-contained flats above. Freehold. Producing £60,000 per annum.</p>
          <p>Auction Thursday 10th September 2026.</p></main>'''
        with patch('collectors.barnett_ross.soup',return_value=BeautifulSoup(html,'lxml')):
            lot=_hydrate('https://www.barnettross.co.uk/property.php?id=2','2026-09-10')
        self.assertIsNotNone(lot)
        self.assertEqual(lot.lot_number,'Lot 2')
        self.assertEqual(lot.annual_rent,60000.0)
        self.assertEqual(lot.status,'CURRENT')


if __name__ == '__main__':
    unittest.main()
