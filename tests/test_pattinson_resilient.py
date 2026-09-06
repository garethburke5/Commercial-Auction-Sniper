import unittest
from bs4 import BeautifulSoup
from unittest.mock import patch

from collectors import pattinson as base
from collectors import pattinson_resilient as resilient


class PattinsonResilientTests(unittest.TestCase):
    def test_fallback_route_is_first_party_commercial_search(self):
        self.assertEqual(resilient.COMMERCIAL_SEARCH, "https://www.pattinson.co.uk/commercial/property-search")

    def test_commercial_search_parser_still_rejects_non_auction_agency_stock(self):
        html = BeautifulSoup("""
        <html><body><h1>422 results</h1>
          <a href='/property/1'>Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, FY3 9DA</a>
          <a href='/property/2'>£12,600 Per Annum (+VAT) Industrial in NE63 Enterprise Centre, Ashington, NE63 8UB</a>
          <a href='/property/3'>Starting Bid£275,000 Residential Development in NN1 St Michaels Avenue, Northampton, NN1 4JQ</a>
        </body></html>
        """, "lxml")
        found, total, ids, _ = base._parse_search_html(html)
        self.assertEqual(total, 422)
        self.assertEqual(set(found), {"https://www.pattinson.co.uk/property/1"})
        self.assertEqual(ids, {"1", "2", "3"})

    def test_wrapper_uses_fallback_when_dedicated_routes_fail(self):
        card = "Starting Bid£110,000 Commercial Development in FY3 Whitegate Drive, Blackpool, Lancashire, FY3 9DA"
        with patch.object(base, "collect", return_value=base.SourceResult(base.SOURCE, "FAILED", [], "blocked")), \
             patch.object(resilient, "_fallback_inventory", return_value=({"https://www.pattinson.co.uk/property/1": card}, 422, 22, "commercial-direct")), \
             patch.object(base, "_enrich", return_value=(base._lot_from_card(card, "https://www.pattinson.co.uk/property/1"), False, None)):
            result = resilient.collect()
        self.assertIn(result.status, {"LIVE", "DEGRADED"})
        self.assertEqual(len(result.lots), 1)
        self.assertIn("commercial-search", result.message)


if __name__ == "__main__":
    unittest.main()
