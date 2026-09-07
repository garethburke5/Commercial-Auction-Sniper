import json
import tempfile
import unittest
from pathlib import Path

from history_database import match_score, update_history_database


class HistoryDatabaseTests(unittest.TestCase):
    def test_address_variants_match_same_property(self):
        self.assertGreaterEqual(
            match_score("33 High Street, Tean, Stoke-On-Trent, ST10 4DY", "33 High St, Upper Tean, Stoke on Trent ST10 4DY"),
            0.78,
        )

    def test_neighbouring_numbers_do_not_auto_merge(self):
        self.assertLess(
            match_score("33 High Street, Tean ST10 4DY", "35 High Street, Tean ST10 4DY"),
            0.78,
        )

    def test_event_preserves_source_link_and_status_transition(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "history.json"
            base = {
                "source": "Auction Estates",
                "url": "https://example.test/property/lot-123",
                "address": "62 Station Street, Kirkby-in-Ashfield, NG17 7AS",
                "auction_date": "2026-10-08",
                "lot_number": "12",
                "guide_price": 80000.0,
                "status": "CURRENT",
                "legal_pack_url": "https://example.test/legal/123",
            }
            update_history_database([base], path=path, observed_at="2026-09-07T09:00:00+00:00")
            sold = dict(base)
            sold["status"] = "SOLD PRIOR"
            update_history_database([sold], path=path, observed_at="2026-09-08T09:00:00+00:00")
            db = json.loads(path.read_text())
            self.assertEqual(len(db["properties"]), 1)
            self.assertEqual(len(db["auction_events"]), 1)
            event = db["auction_events"][0]
            self.assertEqual(event["status"], "SOLD PRIOR")
            self.assertEqual(event["source_evidence"]["listing_url"], base["url"])
            self.assertEqual(event["source_evidence"]["legal_pack_url"], base["legal_pack_url"])
            self.assertEqual([x["status"] for x in event["observations"]], ["CURRENT", "SOLD PRIOR"])

    def test_different_auction_urls_create_multiple_events_for_same_property(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "history.json"
            first = {
                "source": "Pugh",
                "url": "https://example.test/pugh/2024/lot7",
                "address": "33 High Street, Tean, Stoke-on-Trent ST10 4DY",
                "auction_date": "2024-02-15",
                "lot_number": "7",
                "guide_price": 225000,
                "status": "ARCHIVED",
            }
            second = {
                "source": "Auction House",
                "url": "https://example.test/ah/2026/lot21",
                "address": "33 High St, Upper Tean, Stoke on Trent, ST10 4DY",
                "auction_date": "2026-10-08",
                "lot_number": "21",
                "guide_price": 265000,
                "status": "CURRENT",
            }
            db = update_history_database([first, second], path=path, observed_at="2026-09-07T09:00:00+00:00")
            self.assertEqual(len(db["properties"]), 1)
            self.assertEqual(len(db["auction_events"]), 2)
            self.assertEqual(len(db["properties"][0]["address_variants"]), 2)


if __name__ == "__main__":
    unittest.main()
