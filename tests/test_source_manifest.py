import json
import tempfile
import unittest
from pathlib import Path

from source_manifest import append_missing_health, manifest_coverage


class SourceManifestTests(unittest.TestCase):
    def _config(self):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "targets.json"
        path.write_text(json.dumps({"required_sources": ["A", "B"], "expansion_sources": ["C"]}), encoding="utf-8")
        return td, path

    def test_missing_required_source_blocks_acceptance(self):
        td, path = self._config()
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE"}]
        coverage = manifest_coverage(health, path)
        self.assertEqual(coverage["missing_required_sources"], ["B"])
        self.assertFalse(coverage["acceptance_ready"])

    def test_failed_required_source_blocks_acceptance(self):
        td, path = self._config()
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE"}, {"source": "B", "status": "FAILED"}]
        coverage = manifest_coverage(health, path)
        self.assertEqual(coverage["unhealthy_required_sources"], ["B"])
        self.assertFalse(coverage["acceptance_ready"])

    def test_missing_health_is_explicit_not_silent(self):
        td, path = self._config()
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE"}]
        coverage = append_missing_health(health, path)
        self.assertIn("B", {x["source"] for x in health})
        self.assertEqual(next(x for x in health if x["source"] == "B")["status"], "NOT IMPLEMENTED")
        self.assertIn("B", coverage["unhealthy_required_sources"])

    def test_all_required_healthy_is_ready(self):
        td, path = self._config()
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE"}, {"source": "B", "status": "CATALOGUE PENDING"}]
        coverage = manifest_coverage(health, path)
        self.assertTrue(coverage["acceptance_ready"])


if __name__ == "__main__":
    unittest.main()
