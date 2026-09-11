import unittest

from collectors.clive_emson import _parse_occupation, _parse_passing_rent
from property_summary import build_opportunity_summary


TEXT = """
Lot 29 Substantial City Centre Freehold Commercial Building With Income And Asset Management Potential.
GUIDE PRICE £200,000+ FEES. Currently part let at £21,000 per annum. Estimated Rental Value £71,000 per annum.
Commercial Investment. Freehold. Extensive vacant accommodation offering scope for re-letting, subdivision or owner occupation.
Former Co-op/Somerfield and Argos areas providing generous and flexible commercial space.
Part of the building is let to a dance studio with the lease expiring November 2030 at a current rental of £15,000 per annum
and there is a barber's let at a current rental of £6,000 per annum, also expiring November 2030, and with a break in 2028.
It is considered the vacant ground floor level has an estimated rental value of £50,000 per annum.
EPC Ratings C (71). Total Floor Area 1,739 sq.m. B (49). Total Floor Area 76 sq.m. E (122). Total Floor Area 338 sq.m.
Freehold with Part Vacant Possession.
"""


class TruroRegressionTests(unittest.TestCase):
    def test_part_let_total_passing_rent_wins(self):
        self.assertEqual(_parse_passing_rent(TEXT, guide_price=200000), 21000)
        self.assertEqual(_parse_occupation(TEXT), "Part Vacant / Part Let")

    def test_summary_surfaces_asset_management_and_erv(self):
        row = {
            "property_type": "Commercial Investment",
            "occupation": "Part Vacant / Part Let",
            "annual_rent": 21000,
            "description": TEXT,
        }
        title, highlights = build_opportunity_summary(row)
        self.assertEqual(title, "PART-LET COMMERCIAL INVESTMENT + VACANCY")
        joined = " | ".join(highlights)
        self.assertIn("ERV £71,000 p.a.", joined)
        self.assertIn("Asset management", joined)


if __name__ == "__main__":
    unittest.main()
