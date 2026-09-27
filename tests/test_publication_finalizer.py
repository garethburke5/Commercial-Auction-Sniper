import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from run_collectors_resilient import _clean_site_chrome, _finalize_published_snapshot


class PublicationFinalizerTests(unittest.TestCase):
    def test_merged_component_area_cannot_be_published_as_a_portfolio_total(self):
        from collectors.publication_quality import prepare_publication
        row={'source':'Pugh / BTG Eddisons','url':'https://example.test/percy',
             'address':'15–23 Percy Street','description':'Four retail units. Number 15 extends to 1,984 sq ft. Number 17 extends to 500 sq ft.',
             'area_sqft':1984,'area_sqm':184.3}
        result=prepare_publication({'properties':[row]})['properties'][0]
        self.assertIsNone(result['area_sqft'])
        self.assertIsNone(result['area_sqm'])
        row['description']+=' Total floor area 3,100 sq ft.'
        row.update(area_sqft=3100,area_sqm=288)
        self.assertEqual(prepare_publication({'properties':[row]})['properties'][0]['area_sqft'],3100)

    def test_saved_pugh_listing_is_banked_but_never_published_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'properties.json'
            current={'source':'Pugh / BTG Eddisons','url':'https://www.pugh-auctions.com/property/percy',
                     'address':'15 Percy Street','auction_date':'2026-10-28','status':'CURRENT','description':'Retail investment'}
            previous=dict(current,url=current['url']+'/at/2026-09-18_163524',auction_date='2026-09-30')
            path.write_text(json.dumps({'properties':[current,previous],'archive':[]}))
            _finalize_published_snapshot(path,today=date(2026,9,27))
            data=json.loads(path.read_text())
        self.assertEqual(len(data['properties']),1)
        self.assertEqual(len(data['archive']),1)
        self.assertEqual(data['archive'][0]['status'],'ARCHIVED')

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
