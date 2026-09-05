import unittest

from collectors.core import SourceResult
from run_collectors import _run_collector_safely


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


if __name__ == "__main__":
    unittest.main()
