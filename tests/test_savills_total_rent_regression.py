import unittest

from collectors.core import Lot
from collectors.savills_all_future import _enhance_savills_lot, _savills_total_rent


VALE_TEXT = """
6 The Vale Uxbridge Road London W3 7SB. Substantial London Mixed Use Freehold.
Comprises a Retail Unit, a Studio, 2 x 1-Bedrooms and 3 x 2-Bedroom Flats - 3,681 sq ft (342 sqm).
Investment Let at £137,120 per annum (8.84% GIY on Guide Price).
Retail Unit Let for a Term Until November 2031 at a Rent of £20,000 p.a.
Rent £137,120 per annum.
"""


class SavillsTotalRentRegressionTests(unittest.TestCase):
    def test_total_investment_rent_beats_component_retail_rent(self):
        self.assertEqual(_savills_total_rent(VALE_TEXT), 137120.0)
        lot = Lot(
            source="Savills Auctions",
            url="https://auctions.savills.co.uk/auctions/29--30-september-2026-243/6-the-vale-uxbridge-road-london-w3-7sb-24269",
            address="6 The Vale Uxbridge Road London W3 7SB",
            guide_price=1550000.0,
            annual_rent=20000.0,
            tenure="Freehold",
            property_type="Mixed use",
            occupation="Tenanted",
            description=VALE_TEXT,
        )
        lot = _enhance_savills_lot(lot)
        self.assertEqual(lot.annual_rent, 137120.0)
        self.assertAlmostEqual(lot.gross_yield, 8.85, places=2)


if __name__ == "__main__":
    unittest.main()
