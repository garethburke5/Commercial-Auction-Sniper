import unittest

from collectors.clive_emson_resilient import _clive_facts


HAWLEY = """
Lot 74 Offices With Potential For Residential Conversion
15 Hawley Street, Margate, Kent, CT9 1PU
Category Vacant Commercial Tenure Freehold
Old town location Close to seafront Basement has separate access Courtyard garden to rear
The building has previously been used as offices and we understand this building may have potential for permitted development to convert the property into a single residential dwelling or there may be potential for use as a House of Multiple Occupation (HMO), for conversion into multiple self-contained residential units or a boutique hotel, subject to all necessary consents being obtainable.
We have been informed by the seller that the main roof has been replaced within the last 12 months.
EPC Rating D (83). Total Floor Area 156 sq.m.
Freehold with Vacant Possession
"""


class CliveEmsonHawleyRegressionTests(unittest.TestCase):
    def test_hawley_street_extracts_office_conversion_facts(self):
        facts = _clive_facts(HAWLEY, "Lot 74 Offices With Potential For Residential Conversion")
        self.assertEqual(facts["property_type"], "Office")
        self.assertEqual(facts["area_sqm"], 156.0)
        self.assertAlmostEqual(facts["area_sqft"], 1679.2, places=1)
        self.assertEqual(facts["epc"], "D (83)")
        self.assertTrue(facts["residential_conversion"])
        self.assertTrue(facts["development_potential"])
        self.assertIn("Basement with separate access", facts["pitch"])
        self.assertIn("Rear courtyard / yard", facts["pitch"])
        self.assertIn("Old Town location", facts["pitch"])
        self.assertIn("Main roof replaced within last 12 months", facts["pitch"])


if __name__ == "__main__":
    unittest.main()
