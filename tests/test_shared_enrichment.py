import unittest

from collectors.core import Lot
from collectors.utils import enrich_common_fields


class SharedEnrichmentTests(unittest.TestCase):
    def lot(self, **kwargs):
        return Lot(source="Test", url="https://example.test/lot", address="1 High Street", **kwargs)

    def test_explicit_investment_facts_are_enriched(self):
        text = (
            "Freehold retail investment extending to 2,150 sq ft (199.7 sq m). "
            "The shop is let to Example Limited producing £24,000 pa on a full repairing and insuring lease. "
            "EPC Rating C. Rateable Value: £18,500. Rear car park with 6 parking spaces."
        )
        lot = enrich_common_fields(self.lot(annual_rent=24000), text)
        self.assertEqual(lot.property_type, "Retail")
        self.assertEqual(lot.area_sqft, 2150)
        self.assertAlmostEqual(lot.area_sqm, 199.7)
        self.assertEqual(lot.epc, "C")
        self.assertEqual(lot.rateable_value, 18500)
        self.assertEqual(lot.occupation, "Let")
        self.assertTrue(lot.fri)
        self.assertEqual(lot.parking, "6 parking spaces")

    def test_part_let_part_vacant_is_not_marked_wholly_vacant(self):
        text = "Ground floor shop is let to Example Ltd. Upper floor is offered with vacant possession. Mixed-use investment."
        lot = enrich_common_fields(self.lot(annual_rent=12000), text)
        self.assertEqual(lot.occupation, "Part Vacant / Part Let")
        self.assertEqual(lot.property_type, "Mixed Use")

    def test_source_specific_values_are_never_overwritten(self):
        lot = self.lot(area_sqft=999, epc="B", property_type="Medical", occupation="Tenanted")
        enrich_common_fields(lot, "Retail unit 1,200 sq ft. EPC D. Vacant possession.")
        self.assertEqual(lot.area_sqft, 999)
        self.assertEqual(lot.epc, "B")
        self.assertEqual(lot.property_type, "Medical")
        self.assertEqual(lot.occupation, "Tenanted")

    def test_unlabelled_numbers_do_not_become_area_or_rateable_value(self):
        lot = enrich_common_fields(self.lot(), "Auction 17 September 2026. Guide £125,000. Call 020 1234 5678.")
        self.assertIsNone(lot.area_sqft)
        self.assertIsNone(lot.area_sqm)
        self.assertIsNone(lot.rateable_value)

    def test_development_signals_fill_flags(self):
        lot = enrich_common_fields(
            self.lot(),
            "Commercial property with development potential subject to planning and possible residential conversion. "
            "Asset management opportunity. In need of modernisation."
        )
        self.assertTrue(lot.development_potential)
        self.assertTrue(lot.residential_conversion)
        self.assertTrue(lot.asset_management)
        self.assertTrue(lot.refurbishment)


if __name__ == "__main__":
    unittest.main()
