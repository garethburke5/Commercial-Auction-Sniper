import unittest

from collectors.core import Lot, clean_description, normalize_occupation, parse_guide


class CoreQualityNormalisationTests(unittest.TestCase):
    def test_extracts_property_particulars_from_page_chrome(self):
        raw = (
            "2-7 Market Way | Pugh Auctions Book your free appraisal Register to bid My account "
            "Property Details Description A freehold commercial investment opportunity comprising "
            "three retail units and three flats. Units 3 and 7 are sold with vacant possession; "
            "unit 5 is let on a long lease. Costs Auction Details The sale of this property will take place online."
        )
        cleaned = clean_description(raw)
        self.assertTrue(cleaned.startswith("A freehold commercial investment opportunity"))
        self.assertIn("unit 5 is let", cleaned)
        self.assertNotIn("Register to bid", cleaned)
        self.assertNotIn("Auction Details", cleaned)

    def test_generic_key_features_start_removes_leading_controls(self):
        raw = (
            "Home Auctions Login Register to bid My account Book a viewing Key Features "
            "Freehold town centre retail investment let at £24,000 per annum. "
            "Description Ground floor shop with offices above. Auction Deposit and Fees apply."
        )
        cleaned = clean_description(raw)
        self.assertTrue(cleaned.startswith("Freehold town centre retail investment"))
        self.assertNotIn("Register to bid", cleaned)
        self.assertNotIn("Book a viewing", cleaned)
        self.assertNotIn("Auction Deposit", cleaned)

    def test_trailing_transactional_controls_are_cut(self):
        raw = (
            "Description A warehouse investment extending to 5,000 sq ft and let for £30,000 pa. "
            "The tenant has occupied for ten years. Register to bid Add to wishlist Book a viewing"
        )
        cleaned = clean_description(raw)
        self.assertEqual(
            cleaned,
            "A warehouse investment extending to 5,000 sq ft and let for £30,000 pa. The tenant has occupied for ten years."
        )

    def test_normal_property_prose_is_not_truncated_by_fallback_words(self):
        raw = "A commercial investment with a detailed description of the accommodation and location."
        self.assertEqual(clean_description(raw), raw)

    def test_repeated_currency_markers_do_not_hide_guide_price(self):
        self.assertEqual(parse_guide("Guide Price £ £ 295,000"), 295000.0)
        self.assertEqual(parse_guide("Guide: ££125,000"), 125000.0)

    def test_vacant_label_is_repaired_when_particulars_show_part_let(self):
        description = (
            "A mixed-use investment. Units 3 and 7 are sold with vacant possession; "
            "Unit 5 is let to a tenant for 10 years."
        )
        self.assertEqual(normalize_occupation("Vacant", description), "Part Vacant / Part Let")

    def test_part_let_record_keeps_rent_and_yield(self):
        lot = Lot(
            source="Example",
            url="https://example.test/lot/1",
            address="1 High Street, Example EX1 1AA",
            guide_price=200000,
            annual_rent=20000,
            occupation="Vacant",
            description="Part vacant possession; ground-floor shop is let to Example Ltd.",
        ).finalise()
        self.assertEqual(lot.occupation, "Part Vacant / Part Let")
        self.assertEqual(lot.annual_rent, 20000)
        self.assertEqual(lot.gross_yield, 10.0)

    def test_true_vacant_record_still_clears_rent(self):
        lot = Lot(
            source="Example",
            url="https://example.test/lot/2",
            address="2 High Street, Example EX1 1AA",
            guide_price=100000,
            annual_rent=12000,
            occupation="Vacant possession",
            description="A vacant commercial unit requiring refurbishment.",
        ).finalise()
        self.assertEqual(lot.occupation, "Vacant possession")
        self.assertIsNone(lot.annual_rent)
        self.assertIsNone(lot.gross_yield)


if __name__ == "__main__":
    unittest.main()
