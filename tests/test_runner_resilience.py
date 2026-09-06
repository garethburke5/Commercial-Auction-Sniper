import unittest

from collectors.core import SourceResult
from run_collectors import _enrich_item, _run_collector_safely


class RunnerResilienceTests(unittest.TestCase):
    def test_collector_exception_becomes_failed_source_result(self):
        def collect():
            raise TimeoutError("upstream timeout")

        collect.__module__ = "collectors.example_house"
        result = _run_collector_safely(collect)

        self.assertIsInstance(result, SourceResult)
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.lots, [])
        self.assertIn("TimeoutError", result.message)
        self.assertEqual(result.discovered_count, 0)

    def test_successful_collector_passes_through(self):
        expected = SourceResult("Example", "LIVE", [], "ok")

        def collect():
            return expected

        self.assertIs(_run_collector_safely(collect), expected)

    def test_production_fallback_enriches_explicit_particulars_without_overwriting(self):
        item = {
            "source": "Example",
            "url": "https://example.test/lot/1",
            "address": "1 High Street, Example EX1 1AA",
            "description": "Freehold retail investment extending to 2,150 sq ft. EPC C. Let to Example Ltd producing £24,000 pa.",
            "property_type": "Medical",
            "guide_price": 200000.0,
            "annual_rent": 24000.0,
        }
        enriched = _enrich_item(item)
        self.assertEqual(enriched["property_type"], "Medical")
        self.assertEqual(enriched["area_sqft"], 2150.0)
        self.assertEqual(enriched["epc"], "C")
        self.assertEqual(enriched["occupation"], "Let")
        self.assertIsNone(enriched.get("tenure"))


if __name__ == "__main__":
    unittest.main()
