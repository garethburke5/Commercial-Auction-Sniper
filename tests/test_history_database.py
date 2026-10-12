import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from history_database import match_score, update_history_database


class HistoryDatabaseTests(unittest.TestCase):
    def test_index_preserves_variants_neighbours_and_missing_postcodes(self):
        import history_database as history
        rows = [
            ('33 High Street, Tean ST10 4DY', '1'),
            ('35 High Street, Tean ST10 4DY', '2'),
            ('33 High St, Tean ST10 4DY', '3'),
            ('33 High Street, Tean ST11 4DY', '4'),
            ('33 High Street, Tean', '5'),
            ('33 High Street, Tean ST10 4DY', '6'),
        ]
        items=[{'source':'Example','url':'https://example.test/'+n,
                'auction_date':'2026-10-10','address':a,'lot_number':n}
               for a,n in rows]
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'history.json'
            result=history.update_history_database(items,path=path,observed_at='2026-10-10')
            self.assertEqual(len(result['properties']),4)
            self.assertEqual(len(result['auction_events']),6)
            ids=[e['property_id'] for e in result['auction_events']]
            self.assertEqual(ids[0],ids[2]);self.assertEqual(ids[0],ids[5])
            self.assertNotEqual(ids[0],ids[1]);self.assertNotEqual(ids[0],ids[3])

    def test_index_uses_all_variants_and_original_order_on_ties(self):
        import history_database as history
        address='33 High Street, Tean ST10 4DY'
        props=[{'property_id':'first','canonical_address':'33 High Street ST11 4DY',
                'address_variants':['33 High Street ST11 4DY',address]},
               {'property_id':'second','canonical_address':address,'address_variants':[address]}]
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'history.json'
            path.write_text(json.dumps(dict(history.empty_database(),properties=props)))
            result=history.update_history_database([{'source':'Example','url':'https://example.test/1',
                'address':address,'auction_date':'2026-10-10'}],path=path,observed_at='2026-10-10')
            self.assertEqual(result['auction_events'][0]['property_id'],'first')

    def test_rebanking_does_not_compare_every_property(self):
        import history_database as history
        items=[{'source':'Example','url':f'https://example.test/{n}',
                'address':f'1 High Street, AB1 {n:03d}AA',
                'lot_number':str(n),'auction_date':'2026-10-10'} for n in range(100)]
        # Use valid distinct postcode districts and keep exact published addresses.
        for n,item in enumerate(items): item['address']=f'1 High Street, AB{n//10+1} {n%10}AA'
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'history.json'
            first=history.update_history_database(items,path=path,observed_at='2026-10-10')
            with patch.object(history,'match_score',wraps=history.match_score) as score:
                second=history.update_history_database(items,path=path,observed_at='2026-10-11')
            self.assertEqual(score.call_count,100)
            self.assertEqual(len(first['auction_events']),len(second['auction_events']))
            self.assertEqual(second['stats']['added_events_last_run'],0)

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
