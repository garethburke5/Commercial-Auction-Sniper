import unittest
from collectors.pugh import _floor_area_sqft


class PughAreaTests(unittest.TestCase):
    def test_prefers_overall_nia_over_first_unit_measurement(self):
        text = (
            "Ground Floor Retail Unit 1 Sales area 297 sq ft. "
            "Retail Unit 2 392 sq ft. Flat One 594 sq ft. Flat Two 637 sq ft. "
            "Overall NIA: 1,975 sq ft (not including common areas)."
        )
        self.assertEqual(_floor_area_sqft(text), 1975.0)

    def test_uses_largest_plausible_area_when_no_total_label_exists(self):
        text = "Front office 352 sq ft. Rear office 744 sq ft. Building extends to 1,607 sq ft."
        self.assertEqual(_floor_area_sqft(text), 1607.0)


if __name__ == "__main__":
    unittest.main()
