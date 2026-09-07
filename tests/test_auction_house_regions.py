import unittest
from bs4 import BeautifulSoup

from collectors.auction_house_regions import (
    _local_card, _commercialish, _prior_or_withdrawn,
    _card_address, _fallback_catalogue_lot, _direct_first_party_lot,
)


class AuctionHouseRegionTests(unittest.TestCase):
    def test_commercial_road_address_does_not_make_flat_commercial(self):
        text = "Lot 20 Flat 177 Wyndham Court, Commercial Road, Southampton SO15 1GU Apartment 3 Bedrooms Guide £80,000"
        self.assertFalse(_commercialish(text))

    def test_explicit_commercial_property_is_kept(self):
        text = "Lot 15 Auckland House, Southsea PO4 0PP Commercial Property 12 Bedrooms Guide £475,000"
        self.assertTrue(_commercialish(text))

    def test_local_card_does_not_absorb_neighbouring_lots(self):
        html = '''
        <section>
          <article><div>Lot 14 House</div><a href="/x/14">View</a></article>
          <article><div>Lot 15 Commercial Property</div><a href="/x/15">View</a></article>
        </section>
        '''
        s = BeautifulSoup(html, "lxml")
        card = _local_card(s.find("a", href="/x/15"))
        self.assertIn("Lot 15", card)
        self.assertNotIn("Lot 14", card)

    def test_prior_status_is_scoped_to_card(self):
        self.assertTrue(_prior_or_withdrawn("Lot 7 SOLD PRIOR Commercial Property"))
        self.assertFalse(_prior_or_withdrawn("Lot 7 Commercial Property"))

    def test_wales_catalogue_label_recovers_real_address(self):
        label = "*Guide | £120,000 (plus fees) 4 Bed Mixed Use 1 Norfolk Street, Swansea, SA1 6JQ"
        self.assertEqual(_card_address(label, label), "1 Norfolk Street, Swansea, SA1 6JQ")

    def test_catalogue_fallback_preserves_authoritative_guide_type_and_date(self):
        card = "Lot 40 *Guide | £120,000 (plus fees) 4 Bed Mixed Use 1 Norfolk Street, Swansea, SA1 6JQ"
        lot = _fallback_catalogue_lot(
            "Auction House Wales",
            "https://wales.auctionhouse.co.uk/lot/details/03fec6fe-eb63-410a-a98a-df0345efa821",
            card,
            "*Guide | £120,000 (plus fees) 4 Bed Mixed Use 1 Norfolk Street, Swansea, SA1 6JQ",
            "Lot 40",
            "2026-09-09",
        )
        self.assertIsNotNone(lot)
        self.assertEqual(lot.address, "1 Norfolk Street, Swansea, SA1 6JQ")
        self.assertEqual(lot.guide_price, 120000)
        self.assertEqual(lot.property_type, "Mixed Use")
        self.assertEqual(lot.auction_date, "2026-09-09")

    def test_uuid_detail_recovery_keeps_rich_first_party_particulars(self):
        html='''<html><head><meta property="og:image" content="https://wales.auctionhouse.co.uk/images/lot-cardigan.jpg"></head><body>
          <main>
            <h1>Lot 25: 7-8 High Street, Cardigan, SA43 1HJ</h1>
            <p>Retail Investment. Guide Price £275,000. Freehold.</p>
            <p>Ground floor retail unit extending to approximately 2,336 sq ft with four flats above sold off.</p>
            <p>Let to The Works Stores Limited on a five year lease from 10 December 2025 at £33,000 per annum.</p>
            <p>Prominent town centre position.</p>
          </main>
        </body></html>'''
        def fetcher(_url): return BeautifulSoup(html,'lxml')
        lot=_direct_first_party_lot(
            "Auction House Wales",
            "https://wales.auctionhouse.co.uk/lot/details/11111111-1111-1111-1111-111111111111",
            "Lot 25 *Guide | £275,000 Retail Investment 7-8 High Street, Cardigan, SA43 1HJ",
            "7-8 High Street, Cardigan, SA43 1HJ",
            "Lot 25","2026-09-09",fetcher=fetcher,
        )
        self.assertIsNotNone(lot)
        self.assertEqual(lot.address,"7-8 High Street, Cardigan, SA43 1HJ")
        self.assertEqual(lot.guide_price,275000)
        self.assertEqual(lot.annual_rent,33000)
        self.assertEqual(lot.area_sqft,2336)
        self.assertEqual(lot.tenure,"Freehold")
        self.assertIsNotNone(lot.image_url)

    def test_uuid_detail_recovery_extracts_mixed_use_and_listed_status(self):
        html='''<main><h1>20 The Struet, Brecon, LD3 7LL</h1>
        <p>Mixed Use. Guide £99,000. Freehold Grade II Listed property.</p>
        <p>Vacant ground floor commercial accommodation with a two bedroom apartment above. Development potential STP.</p></main>'''
        lot=_direct_first_party_lot(
            "Auction House Wales","https://wales.auctionhouse.co.uk/lot/details/22222222-2222-2222-2222-222222222222",
            "Lot 45 Mixed Use Guide £99,000","20 The Struet, Brecon, LD3 7LL","Lot 45","2026-09-09",
            fetcher=lambda _url: BeautifulSoup(html,'lxml'))
        self.assertEqual(lot.property_type,"Mixed Use")
        self.assertEqual(lot.listed_status,"Grade II Listed")
        self.assertTrue(lot.development_potential)


if __name__ == "__main__":
    unittest.main()
