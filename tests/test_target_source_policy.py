import json
import unittest
from pathlib import Path

from source_manifest import manifest_coverage


class TargetSourcePolicyTests(unittest.TestCase):
    def test_dedman_gray_is_represented_by_verified_bidx1_successor(self):
        health = [{"source": "BidX1", "status": "LIVE"}]
        coverage = manifest_coverage(health)
        self.assertNotIn("Dedman Gray", coverage["missing_expansion_sources"])
        self.assertEqual(coverage["resolved_source_aliases"].get("Dedman Gray"), "BidX1")

    def test_andersons_is_documented_as_non_auction_lead_not_target(self):
        data = json.loads(Path("config/target_sources.json").read_text(encoding="utf-8"))
        self.assertNotIn("Andersons", data["expansion_sources"])
        explanation = data.get("assessed_non_auction_sources", {}).get("Andersons", "")
        self.assertIn("does not conduct property auctions", explanation)

    def test_newly_implemented_expansion_sources_remain_acceptance_targets(self):
        data = json.loads(Path("config/target_sources.json").read_text(encoding="utf-8"))
        for source in ("BidX1", "Symonds & Sampson", "Auction Estates"):
            self.assertIn(source, data["expansion_sources"])


if __name__ == "__main__":
    unittest.main()
