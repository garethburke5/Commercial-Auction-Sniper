import unittest

from collectors.core import Lot
from collectors.savills_all_future import _enhance_savills_lot
from property_summary import build_opportunity_summary


HANOVER_TEXT = """
Hanover House Queen Charlotte Street Bristol BS1 4EX.
Refurbished reversionary multi-let office building in Bristol's central business district.
Comprising 18,414 sq ft in Total. Investment Part Let at £183,908 p.a.
Includes 11,178 sq ft offices offered vacant. Total Floor Area 18,414 sq ft of which
11,178 sq ft is currently vacant. EPC Rating B. VAT is Applicable to this Lot.
The building was comprehensively refurbished in 2020 at a cost of £2.2 million.
Long Leasehold held on a lease from British Telecommunications plc for a term of
150 years from 25.12.1990, thus having approximately 114 years unexpired, at a
fixed annual ground rent of £1. On-site surface parking for 8 cars with 4 EV
charging points, plus cycle storage (30 spaces) and showers.
"""


class SavillsHanoverRegressionTests(unittest.TestCase):
    def _lot(self):
        return Lot(
            source="Savills Auctions",
            url="https://auctions.savills.co.uk/auctions/29--30-september-2026-243/hanover-house-queen-charlotte-street-bristol-bs1-4ex-24112",
            address="Hanover House Queen Charlotte Street Bristol BS1 4EX",
            guide_price=3750000.0,
            annual_rent=183908.0,
            tenure="Leasehold",
            property_type="Office",
            occupation="Tenanted",
            vat_status="APPLICABLE",
            description=HANOVER_TEXT,
        )

    def test_hanover_material_facts_are_captured(self):
        lot = _enhance_savills_lot(self._lot())
        self.assertEqual(lot.property_type, "Office")
        self.assertEqual(lot.tenure, "Long Leasehold")
        self.assertEqual(lot.occupation, "Part Vacant / Part Let")
        self.assertEqual(lot.area_sqft, 18414.0)
        self.assertEqual(lot.epc, "B")
        self.assertEqual(lot.ground_rent, 1.0)
        self.assertEqual(lot.lease_start, "25.12.1990")
        self.assertEqual(lot.lease_term, "150 years (approx. 114 years unexpired)")
        self.assertTrue(lot.refurbishment)
        self.assertIn("8 cars", lot.parking)
        self.assertIn("4 EV charging points", lot.parking)
        self.assertIn("30 cycle spaces", lot.parking)
        self.assertAlmostEqual(lot.gross_yield, 4.90, places=2)

    def test_hanover_is_not_ground_rent_investment(self):
        lot = _enhance_savills_lot(self._lot())
        row = lot.to_dict()
        headline, highlights = build_opportunity_summary(row)
        self.assertEqual(headline, "PART-LET OFFICE INVESTMENT + VACANCY")
        self.assertNotEqual(headline, "GROUND RENT INVESTMENT")
        self.assertTrue(any("11,178 sq ft vacant" in item for item in highlights))

    def test_incidental_one_pound_ground_rent_does_not_drive_asset_type(self):
        row = {
            "property_type": "Office",
            "occupation": "Part Vacant / Part Let",
            "annual_rent": 183908.0,
            "description": "Office investment let at £183,908 pa. Long leasehold at a fixed annual ground rent of £1.",
        }
        headline, _ = build_opportunity_summary(row)
        self.assertEqual(headline, "PART-LET OFFICE INVESTMENT + VACANCY")
        self.assertNotEqual(headline, "GROUND RENT INVESTMENT")


if __name__ == "__main__":
    unittest.main()
