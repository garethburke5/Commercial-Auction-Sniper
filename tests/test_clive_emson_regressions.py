import unittest

from collectors.clive_emson import _parse_occupation, _parse_passing_rent
from collectors.core import Lot, parse_guide


class CliveEmsonRegressionTests(unittest.TestCase):
    def test_lot_113_current_rent_beats_guide_price(self):
        text = (
            "Lot 113 Pair Of Shops And Self-Contained Flat For Investment With Part Vacant Possession "
            "67-69 High Street, Minster, Ramsgate, Kent, CT12 4AB "
            "Auction Ends: 24th September 2026 GUIDE PRICE £250,000+ + FEES "
            "Currently let at £11,880 per annum "
            "Category Mixed Commercial/Residential Tenure Freehold "
            "67 High Street (The Dogg Shop) Tenancy Let on a license agreement at £390 per calendar month. "
            "69 High Street (Mini-Land) Tenancy Let on the terms of a five-year lease from 1st May 2024 "
            "at a current rental of £600 per calendar month. "
            "69A High Street Tenancy Currently vacant."
        )
        guide = parse_guide(text)
        rent = _parse_passing_rent(text, guide_price=guide)
        occupation = _parse_occupation(text)

        self.assertEqual(guide, 250000.0)
        self.assertEqual(rent, 11880.0)
        self.assertEqual(occupation, "Part Vacant / Part Let")

        lot = Lot(
            source="Clive Emson",
            url="https://www.cliveemson.co.uk/properties/268/113/",
            address="67-69 High Street, Minster, Ramsgate, Kent, CT12 4AB",
            guide_price=guide,
            annual_rent=rent,
            occupation=occupation,
            description=text,
        ).finalise()
        self.assertEqual(lot.annual_rent, 11880.0)
        self.assertEqual(lot.gross_yield, 4.75)

    def test_monthly_tenancies_are_aggregated_when_total_missing(self):
        text = (
            "Guide Price £250,000. Mixed commercial/residential investment with part vacant possession. "
            "The Dogg Shop is Let on a license agreement at £390 per calendar month. "
            "Mini-Land is Let on a five-year lease at a current rental of £600 per calendar month. "
            "The flat is currently vacant."
        )
        rent = _parse_passing_rent(text, guide_price=250000)
        self.assertEqual(rent, 11880.0)
        self.assertEqual(_parse_occupation(text), "Part Vacant / Part Let")

    def test_guide_collision_is_rejected(self):
        text = "Guide Price £250,000. Buyer information may refer to £250,000 per annum in unrelated page chrome."
        self.assertIsNone(_parse_passing_rent(text, guide_price=250000))

    def test_wholly_vacant_lot_remains_vacant(self):
        text = "Vacant public house opportunity. The property is offered with vacant possession."
        self.assertEqual(_parse_occupation(text), "Vacant")


if __name__ == "__main__":
    unittest.main()
