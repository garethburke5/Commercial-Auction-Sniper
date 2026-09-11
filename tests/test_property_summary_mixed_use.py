import unittest

from property_summary import build_opportunity_summary


class MixedUseSummaryRegressionTests(unittest.TestCase):
    def test_hastings_mixed_use_surfaces_composition_and_conversion_potential(self):
        row = {
            "property_type": "Mixed Commercial/Residential",
            "occupation": "Vacant",
            "description": (
                "Mixed Residential And Commercial Building With Potential. Bedrooms x 4 Bathrooms x 2. "
                "A four storey mixed-use property comprising ground floor retail accommodation with mezzanine "
                "storage room, together with a maisonette arranged over three upper floors, along with basement "
                "accommodation and rear yard. The property is considered to offer potential for reconfiguration, "
                "conversion or alternative uses, subject to all necessary consents being obtainable. "
                "Third Floor Bedroom with a glazed door leading to roof terrace. Freehold with Vacant possession."
            ),
        }
        headline, highlights = build_opportunity_summary(row)
        self.assertEqual(headline, "VACANT MIXED-USE + CONVERSION OPPORTUNITY")
        joined = " | ".join(highlights)
        self.assertIn("Ground-floor retail + upper-floor maisonette", joined)
        self.assertIn("4 beds / 2 baths", joined)
        self.assertIn("Reconfiguration / conversion / alternative-use potential STC", joined)


if __name__ == "__main__":
    unittest.main()
