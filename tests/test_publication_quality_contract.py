import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import run_collectors as pipeline
from collectors.core import Lot, SourceResult
from collectors.publication_resilience import apply
from run_collectors_resilient import _finalize_published_snapshot


class PublicationQualityContractTests(unittest.TestCase):
    def test_recent_barnard_result_mentions_do_not_turn_housing_or_adjacent_land_into_commercial(self):
        from collectors.publication_quality import publication_exclusion
        base={'source':'Barnard Marcus','address':'Example property','property_type':'Commercial'}
        excluded=[
            'Freehold parcel of land. Adjoining Example Park Hotel. Potential subject to consent. No established commercial use.',
            'Part completed development. The former pub has permission for conversion into three terraced dwellings.',
            '7 bedroom home with a cottage. There is scope to re-instate a care home subject to consent.',
        ]
        for description in excluded:
            with self.subTest(description=description):
                self.assertIsNotNone(publication_exclusion(base|{'description':description}))
        for description in [
            'Freehold mixed-use premises with an existing ground floor retail shop and flat. Residential planning permission also exists.',
            'Freehold hotel investment adjoining a country park.',
            'Land currently let for cruise car parking. Residential planning permission also exists.',
        ]:
            with self.subTest(description=description):
                self.assertIsNone(publication_exclusion(base|{'description':description}))

    def test_runner_and_finalizers_measure_the_published_active_rows(self):
        current = Lot("Example", "https://example.test/lot/1", "1 High Street, EX1 1AA",
                      auction_date="2099-10-01", image_url="https://example.test/front.jpg",
                      guide_price=200000, annual_rent=20000, tenure="Freehold",
                      property_type="Retail", description="Retail shop investment")
        terminal = Lot("Example", "https://example.test/lot/2", "2 High Street, EX1 1AA",
                       auction_date="2099-10-01", status="SOLD PRIOR", description="Retail shop")
        result = SourceResult("Example", "LIVE", [current, terminal],
                              expected_count=2, authoritative_snapshot=True,
                              scope_dates=("2099-10-01",))
        with tempfile.TemporaryDirectory() as tmp, patch.object(pipeline, "DATA", Path(tmp)), \
             patch.object(pipeline, "COLLECTORS", [lambda: result]):
            pipeline.run()
            path = Path(tmp) / "properties.json"
            _finalize_published_snapshot(path, today=date(2026, 9, 20))
            data = apply(path, today=date(2026, 9, 20))
            saved = json.loads(path.read_text())
        self.assertEqual(len(data["properties"]), 2)
        quality = saved["integrity"]["source_quality"]["Example"]
        self.assertEqual(quality["lots"], 1)
        self.assertEqual(quality["valid_images"], 1)
        self.assertEqual(quality["image_coverage_pct"], 100)
        self.assertEqual(quality["rich_coverage_pct"], 100)
        self.assertEqual(saved["quality"]["source_quality"], saved["integrity"]["source_quality"])

    def test_rejections_are_preserved_in_validator_contract(self):
        data = {"properties": [], "quality": {"rejections": 2, "rejection_reasons": {"invalid_url": 2}}}
        pipeline.refresh_quality_telemetry(data)
        self.assertEqual(data["integrity"]["quality_rejections"], 2)
        self.assertEqual(data["integrity"]["quality_rejection_reasons"], {"invalid_url": 2})

    def test_expired_harman_lots_stay_excluded_after_the_fixture_date(self):
        from bs4 import BeautifulSoup
        from collectors.harman_healy import _lots_from_soup
        page = BeautifulSoup('<section><h3>Lot 1 | End Time - 17/09/2026</h3>'
                             '<p>Retail shop, 1 High Street, EX1 1AA</p></section>', 'lxml')
        with patch('collectors.harman_healy.date', wraps=date) as clock:
            clock.today.return_value = date(2026, 9, 20)
            self.assertEqual(_lots_from_soup(page, 'https://example.test', date(2026, 9, 17)), ([], 0, 0))


if __name__ == "__main__":
    unittest.main()
