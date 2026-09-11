import unittest

from run_collectors_resilient import _lot_identity, _record_score


class PublicationDedupRegressionTests(unittest.TestCase):
    def test_same_lot_with_variant_urls_has_same_identity(self):
        a = {
            "source": "Allsop Commercial", "auction_date": "2026-10-01",
            "lot_number": "Lot 32", "address": "Sheffield S10",
            "url": "https://example.test/lot/32?a=1",
        }
        b = dict(a, url="https://example.test/property/sheffield-s10-lot-32")
        self.assertEqual(_lot_identity(a), _lot_identity(b))

    def test_richer_duplicate_wins(self):
        sparse = {"description": "short"}
        rich = {
            "description": "full particulars " * 80,
            "image_url": "https://example.test/property.jpg",
            "guide_price": 250000,
            "annual_rent": 30000,
            "tenure": "Freehold",
        }
        self.assertGreater(_record_score(rich), _record_score(sparse))


if __name__ == "__main__":
    unittest.main()
