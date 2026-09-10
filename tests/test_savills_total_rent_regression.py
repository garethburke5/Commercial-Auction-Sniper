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

RUNCORN_TEXT = """
Link Bridge Trident Retail & Leisure Park Runcorn WA7 2FQ.
A Freehold retail parade forming part of Trident Retail Park. The property comprises 7 retail units and 1 office unit.
Asset management potential to proactively let out the vacant space and implement a number of rent reviews.
Investment let at £211,505 p.a. (Part vacant).
Investment let at £211,505 p.a. (42.30% GIY on guide).
VAT is applicable However we believe the sale can be treated as a TOGC.
"""


class SavillsTotalRentRegressionTests(unittest.TestCase):
    def test_total_investment_rent_beats_component_retail_rent(self):
        self.assertEqual(_savills_total_rent(VALE_TEXT), 137120.0)
        lot = Lot(source="Savills Auctions",url="https://auctions.savills.co.uk/auctions/29--30-september-2026-243/6-the-vale-uxbridge-road-london-w3-7sb-24269",address="6 The Vale Uxbridge Road London W3 7SB",guide_price=1550000.0,annual_rent=20000.0,tenure="Freehold",property_type="Mixed use",occupation="Tenanted",description=VALE_TEXT)
        lot = _enhance_savills_lot(lot)
        self.assertEqual(lot.annual_rent, 137120.0)
        self.assertAlmostEqual(lot.gross_yield, 8.85, places=2)

    def test_runcorn_part_vacant_investment_keeps_passing_rent(self):
        self.assertEqual(_savills_total_rent(RUNCORN_TEXT), 211505.0)
        lot = Lot(source="Savills Auctions",url="https://auctions.savills.co.uk/auctions/29--30-september-2026-243/link-bridge-trident-retail-leisure-park-runcorn-wa7-2fq-23531",address="Link Bridge Trident Retail & Leisure Park Runcorn WA7 2FQ",guide_price=500000.0,annual_rent=None,tenure="Freehold",property_type="Retail",occupation="Vacant",vat_status="APPLICABLE",description=RUNCORN_TEXT,asset_management=True)
        lot = _enhance_savills_lot(lot)
        self.assertEqual(lot.annual_rent, 211505.0)
        self.assertEqual(lot.occupation, "Part Vacant / Part Let")
        self.assertAlmostEqual(lot.gross_yield, 42.30, places=2)
        self.assertEqual(lot.vat_status, "APPLICABLE")


if __name__ == "__main__": unittest.main()
