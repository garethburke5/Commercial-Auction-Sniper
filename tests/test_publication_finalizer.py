import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from run_collectors_resilient import _clean_site_chrome, _finalize_published_snapshot


class PublicationFinalizerTests(unittest.TestCase):
    def test_residual_site_chrome_is_removed(self):
        text = (
            "Prime retail investment let to Example Ltd at £20,000 per annum with a five year lease. "
            "Further particulars continue here. Register to bid Login Your bid Wishlist"
        )
        cleaned = _clean_site_chrome(text)
        self.assertIn("Prime retail investment", cleaned)
        self.assertNotIn("Register to bid", cleaned)
        self.assertNotIn("Login", cleaned)
        self.assertNotIn("Wishlist", cleaned)

    def test_future_terminal_commercial_rows_remain_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "properties.json"
            payload = {
                "generated_at": "2026-09-10T12:00:00+00:00",
                "properties": [
                    {"source": "Example", "url": "https://x/live", "auction_date": "2026-10-08", "status": "CURRENT", "description": "Live commercial lot"}
                ],
                "archive": [
                    {"source": "Auction House London", "url": "https://x/sold", "auction_date": "2026-10-08", "status": "SOLD PRIOR", "description": "Commercial investment"},
                    {"source": "Auction House London", "url": "https://x/withdrawn", "auction_date": "2026-10-08", "status": "WITHDRAWN", "description": "Shop investment"},
                    {"source": "Auction House London", "url": "https://x/postponed", "auction_date": "2026-10-08", "status": "POSTPONED", "description": "Office investment"},
                    {"source": "Old", "url": "https://x/old", "auction_date": "2026-08-01", "status": "SOLD PRIOR", "description": "Historic lot"},
                    {"source": "Old", "url": "https://x/archived", "auction_date": "2026-10-08", "status": "ARCHIVED", "description": "Archived lot"},
                ],
                "source_health": [],
                "integrity": {},
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            moved = _finalize_published_snapshot(path, today=date(2026, 9, 10))
            result = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(moved, 3)
        statuses = {x["status"] for x in result["properties"]}
        self.assertTrue({"CURRENT", "SOLD PRIOR", "WITHDRAWN", "POSTPONED"}.issubset(statuses))
        self.assertEqual(len(result["properties"]), 4)
        self.assertEqual(len(result["archive"]), 2)
        self.assertEqual(result["integrity"]["terminal_rows_restored_to_publication"], 3)


if __name__ == "__main__":
    unittest.main()
