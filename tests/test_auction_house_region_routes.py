import unittest

from collectors.auction_house_regions import _commercialish, _is_event_href, _is_lot_href


class AuctionHouseRegionalRouteTests(unittest.TestCase):
    def test_date_and_event_id_catalogue_routes_are_accepted(self):
        self.assertTrue(_is_event_href('/wales/auction/2026/9/9', 'wales'))
        self.assertTrue(_is_event_href('/cumbria/auction/lots/9100', 'cumbria'))
        self.assertFalse(_is_event_href('/cumbria/auction/2026/9/10', 'wales'))

    def test_canonical_and_legacy_lot_routes_are_accepted(self):
        self.assertTrue(_is_lot_href('/cumbria/auction/lot/151250', 'cumbria'))
        self.assertTrue(_is_lot_href('https://wales.auctionhouse.co.uk/lot/redirect/360843', 'wales'))
        self.assertTrue(_is_lot_href('https://wales.auctionhouse.co.uk/lot/360843', 'wales'))
        self.assertFalse(_is_lot_href('https://cumbria.auctionhouse.co.uk/lot/360843', 'wales'))

    def test_mixed_use_card_is_commercial(self):
        self.assertTrue(_commercialish('Guide £115,000 · 3 Bed Mixed Use · High Street'))
        self.assertFalse(_commercialish('Guide £115,000 · 3 Bed Terraced House · Commercial Road'))


if __name__ == '__main__':
    unittest.main()
