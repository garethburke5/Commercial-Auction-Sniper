import unittest

from collectors.core import Lot
from collectors.symonds_sampson_resilient import _enrich_land_and_garage_lot


class SymondsArmouryYardRegressionTests(unittest.TestCase):
    def test_site_and_garage_areas_are_not_conflated(self):
        text = (
            "Armoury Yard Shaftesbury Dorset SP7. Guide Price £30,000. "
            "A block of 5 garages and a hardstanding area. Approximately 0.12 acres (519.66m²). "
            "Comprising a block of 5 garages (approx. 1,083sqft. (100.6sqm) overall). "
            "Vehicular access from Victoria Street. Scope for a range of uses (subject to planning permission)."
        )
        lot = Lot(
            source="Symonds & Sampson",
            url="https://auctions.symondsandsampson.co.uk/property/dwr0007cd/sp7/shaftesbury/armoury-yard/land",
            address="Armoury Yard Shaftesbury, Dorset, SP7",
            guide_price=30000,
            tenure="Freehold",
            description=text,
            area_sqft=5594,
            property_type="Commercial",
        )
        lot = _enrich_land_and_garage_lot(lot)
        self.assertEqual(lot.property_type, "Garages / Land")
        self.assertEqual(lot.area_sqft, 1083.0)
        self.assertAlmostEqual(lot.site_area_acres, 0.12, places=2)
        self.assertTrue(lot.development_potential)
        self.assertIn("Victoria Street", lot.parking)


if __name__ == "__main__":
    unittest.main()
