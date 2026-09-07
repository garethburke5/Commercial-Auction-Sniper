import unittest
from datetime import date
from bs4 import BeautifulSoup

from collectors.symonds_sampson import _discover_events, EVENT_INDEXES


class SymondsEventFallbackTests(unittest.TestCase):
    def test_canonical_event_index_recovers_when_upcoming_query_is_empty(self):
        canonical = '''<html><body>
          <div><p>Thursday, 24 September 2026 2:00 PM - 5:00 PM</p><a href="/event/property-auction-sep2026">View Event</a></div>
          <div><p>Thursday, 08 October 2026 2:00 PM - 5:00 PM</p><a href="/event/property-auction-oct2026">View Event</a></div>
        </body></html>'''
        empty = '<html><body><p>No events returned</p></body></html>'

        def fetcher(url):
            return BeautifulSoup(canonical if url == EVENT_INDEXES[0] else empty, 'lxml')

        events, failures = _discover_events(fetcher=fetcher, today=date(2026, 9, 7))
        self.assertFalse(failures)
        self.assertEqual(set(events.values()), {'2026-09-24', '2026-10-08'})

    def test_one_index_route_failure_does_not_fail_discovery(self):
        html = '''<div><p>Thursday, 08 October 2026 2:00 PM - 5:00 PM</p>
        <a href="/event/property-auction-oct2026">View Event</a></div>'''

        def fetcher(url):
            if url == EVENT_INDEXES[0]:
                raise RuntimeError('temporary transport failure')
            return BeautifulSoup(html, 'lxml')

        events, failures = _discover_events(fetcher=fetcher, today=date(2026, 9, 7))
        self.assertEqual(list(events.values()), ['2026-10-08'])
        self.assertEqual(len(failures), 1)


if __name__ == '__main__':
    unittest.main()
