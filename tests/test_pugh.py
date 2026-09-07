import unittest
from bs4 import BeautifulSoup

from collectors.core import Lot
from collectors.pugh import _floor_area_sqft, _apply_pugh_particulars


class PughCollectorRegressionTests(unittest.TestCase):
    def test_overall_nia_beats_individual_unit_measurements(self):
        text = (
            "Ground Floor Retail Unit 1 Sales/till area: 297 sq ft Kitchen: 55 sq ft "
            "Ground Floor Retail Unit 2 Sales/treatment rooms: 354 sq ft Kitchen: 38 sq ft "
            "Flat One Total GIA: 594 sq ft Flat Two Total GIA: 637 sq ft "
            "Overall NIA: 1,975 sq ft"
        )
        self.assertEqual(_floor_area_sqft(text), 1975.0)

    def test_total_gia_parenthetical_sqft_is_used(self):
        text = (
            "Ground Floor - 73.89 Sq.M First Floor 75.46 Sq.M "
            "TOTAL Gross Internal Floor Area 149.35 Sq.M (1,607 sqft)"
        )
        self.assertEqual(_floor_area_sqft(text), 1607.0)

    def test_total_gia_sqm_converts_when_sqft_absent(self):
        sqft = _floor_area_sqft("TOTAL Gross Internal Floor Area 149.35 Sq.M")
        self.assertAlmostEqual(sqft, 149.35 * 10.7639, places=1)

    def test_meadowhead_enrichment_captures_material_facts(self):
        html = """
        <main>
          <h1>356 Meadowhead, Sheffield, South Yorkshire S8 7UJ</h1>
          <p>An extended two storey office building with 11 parking spaces.</p>
          <p>The property provides just over 1,600 sq ft of accommodation over two levels
             that was previously occupied by a letting agent and potential is offered for
             own occupation, investment or possible conversion.</p>
          <p>The building was reroofed in 2025.</p>
          <p>TOTAL Gross Internal Floor Area 149.35 Sq.M (1,607 sqft)</p>
          <p>Vehicular access to rear secure gated car park.</p>
        </main>
        """
        lot = Lot(
            source="Pugh / BTG Eddisons",
            url="https://www.pugh-auctions.com/property/example",
            address="356 Meadowhead, Sheffield, South Yorkshire S8 7UJ",
            auction_date="2026-10-13",
            guide_price=325000,
        )
        out = _apply_pugh_particulars(lot, BeautifulSoup(html, "lxml"))
        self.assertEqual(out.area_sqft, 1607.0)
        self.assertEqual(out.parking, "11 parking spaces")
        self.assertEqual(out.occupation, "Vacant")
        self.assertEqual(out.property_type, "Office")
        self.assertTrue(out.asset_management)
        self.assertTrue(out.refurbishment)

    def test_tean_current_gross_income_is_preferred(self):
        html = """
        <main>
          <p>A freehold mixed use investment opportunity comprising two apartments and two
             commercial units: current gross income £27,600pa.</p>
          <p>33 High Street is let at £6,000 pa. 33a High Street is let at £6,000 pa.</p>
          <p>Overall NIA: 1,975 sq ft</p>
        </main>
        """
        lot = Lot(
            source="Pugh / BTG Eddisons",
            url="https://www.pugh-auctions.com/property/example2",
            address="33 & 33a High Street, Tean, Stoke-On-Trent ST10 4DY",
            auction_date="2026-10-28",
            guide_price=265000,
        )
        out = _apply_pugh_particulars(lot, BeautifulSoup(html, "lxml"))
        self.assertEqual(out.annual_rent, 27600.0)
        self.assertEqual(out.area_sqft, 1975.0)
        self.assertEqual(out.property_type, "Mixed Use")


if __name__ == "__main__":
    unittest.main()
