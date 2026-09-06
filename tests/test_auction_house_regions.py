import unittest
from bs4 import BeautifulSoup

from collectors.auction_house_regions import _local_card, _commercialish, _prior_or_withdrawn


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


if __name__ == "__main__":
    unittest.main()
