import unittest

from collectors.core import Lot, SourceResult
from run_collectors_resilient import _apply_bidx1_reserve_proxy


class BidX1ReserveProxyTests(unittest.TestCase):
    def test_reserve_used_only_when_guide_missing(self):
        lot = Lot(
            source="BidX1",
            url="https://bidx1.com/en/en-gb/auction/property/123456",
            address="Garages at Vernon Close, St Albans, Hertfordshire, AL1 1PB",
            guide_price=None,
            annual_rent=8640,
            tenure="Virtual Freehold",
            description="Reserve £210,000 Commercial investment garages.",
        )
        result = SourceResult("BidX1", "LIVE", [lot])
        _apply_bidx1_reserve_proxy(result)
        self.assertEqual(lot.guide_price, 210000.0)
        self.assertAlmostEqual(lot.gross_yield, 4.11, places=2)
        self.assertIn("no guide price published", lot.description.lower())
        self.assertIn("price/yield proxy", lot.description.lower())

    def test_published_guide_beats_reserve(self):
        lot = Lot(
            source="BidX1",
            url="https://bidx1.com/en/en-gb/auction/property/654321",
            address="Example Commercial Lot",
            guide_price=200000,
            annual_rent=10000,
            description="Guide Price £200,000 Reserve £210,000",
        )
        result = SourceResult("BidX1", "LIVE", [lot])
        _apply_bidx1_reserve_proxy(result)
        self.assertEqual(lot.guide_price, 200000)
        self.assertNotIn("price/yield proxy", lot.description.lower())


if __name__ == "__main__":
    unittest.main()
