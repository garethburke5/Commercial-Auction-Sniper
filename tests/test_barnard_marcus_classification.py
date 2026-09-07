import unittest

from collectors.barnard_marcus import _is_target_particulars, _sale_summary


class BarnardMarcusClassificationTests(unittest.TestCase):
    def test_residential_flat_is_not_rescued_by_location_restaurants(self):
        text = (
            "Long leasehold second floor flat. "
            "Location: Shopping amenities are available locally with a further range of shops, "
            "bars and restaurants found within Notting Hill."
        )
        self.assertFalse(_is_target_particulars(text))

    def test_mixed_use_shop_and_flats_is_included(self):
        text = (
            "Freehold mixed-use building with ground floor shop. "
            "Upper residential parts sold off on a lease. Investment (Rent reserved: £36,000 per annum). "
            "Location: The property occupies a prominent trading position."
        )
        self.assertTrue(_is_target_particulars(text))

    def test_sale_summary_stops_before_location_chrome(self):
        text = "Freehold three-storey mixed-use building. Location: shops bars restaurants retail parade."
        self.assertNotIn("restaurants", _sale_summary(text).lower())


if __name__ == "__main__":
    unittest.main()
