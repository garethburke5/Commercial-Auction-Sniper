import unittest
from bs4 import BeautifulSoup

from collectors.barnard_marcus import _is_target_particulars, _sale_summary, _parse_detail


def page(summary, price='Guide Price £70,000–£80,000'):
    return BeautifulSoup(f'''<html><title>22, Auction: 15th October 2026.</title>
        <h1>59 Norfolk Street, Wisbech</h1>
        <div class="lot-details__price">{price} Tenure: Freehold</div>
        <div class="lot-details__gallery-carousel">
          <div class="lot-gallery__item"><img data-srcset="/front.jpg?w=320 320w, /front.jpg?w=1440 1440w"></div>
          <div class="lot-gallery__item"><img src="/floorplan.jpg"></div>
        </div>
        <div class="lot-summary__description">{summary}</div>
        <footer>Other lots: Sold Prior, Withdrawn. General fees inclusive of VAT.</footer>
        </html>''','html.parser')


URL='https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/123456/'


class BarnardMarcusClassificationTests(unittest.TestCase):
    def test_scoped_particulars_retain_range_income_and_first_gallery_image(self):
        lot=_parse_detail(page('Freehold mixed-use building. Location: Close to a railway station. '
            'Description: Ground floor shop and flat above. Tenancy: Shop let to Example Ltd for a term of 10 years '
            'from 1 January 2023. Rent reserved: £12,000 per annum. EPC Rating: C. '
            'Important Notice: A fee of £1,800 inclusive of VAT is payable.'),URL)
        self.assertEqual((lot.guide_price,lot.guide_price_upper),(70000,80000))
        self.assertEqual(lot.annual_rent,12000)
        self.assertEqual(lot.lease_term,'10 years')
        self.assertEqual(lot.lease_start,'1 January 2023')
        self.assertEqual(lot.epc,'C')
        self.assertEqual(lot.status,'CURRENT')
        self.assertEqual(lot.vat_status,'UNKNOWN')
        self.assertTrue(lot.image_is_primary)
        self.assertEqual(lot.image_url,'https://www.barnardmarcusauctions.co.uk/front.jpg?w=1440')
        self.assertIn('Freehold mixed-use',lot.description)
        self.assertNotIn('railway station',lot.description)

    def test_terminal_commercial_lots_are_retained_with_their_own_status(self):
        for label in ['Sold Prior','Withdrawn','Postponed']:
            with self.subTest(label=label):
                lot=_parse_detail(page('Freehold ground floor shop. Vacant possession.',label),URL)
                self.assertEqual(lot.status,label.upper())
                self.assertIsNone(lot.annual_rent)

    def test_current_october_102_flat_is_not_classified_from_neighbourhood_shops(self):
        self.assertIsNone(_parse_detail(page('Leasehold second floor flat. 38 years remaining on the lease. '
            'Location: Near shops, bars and restaurants. Accommodation: Two bedrooms, reception room, kitchen, bathroom/wc. '
            'Lease: 99 years from 25/12/1965. Important Notice: Fees apply.'),URL))

    def test_missing_particulars_is_a_fetch_failure_not_a_noncommercial_lot(self):
        with self.assertRaisesRegex(ValueError,'particulars'):
            _parse_detail(BeautifulSoup('<h1>Temporary page</h1>','html.parser'),URL)

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
