import json
import tempfile
import unittest
from pathlib import Path

from source_manifest import append_missing_health, manifest_coverage


class SourceManifestTests(unittest.TestCase):
    def _config(self, aliases=None):
        td = tempfile.TemporaryDirectory()
        path = Path(td.name) / "targets.json"
        payload = {"required_sources": ["A", "B"], "expansion_sources": ["C"]}
        if aliases:
            payload["source_aliases"] = aliases
        path.write_text(json.dumps(payload), encoding="utf-8")
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

    def test_verified_successor_alias_satisfies_required_source(self):
        td, path = self._config({"B": "A"})
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE", "lots_seen": 7}]
        coverage = manifest_coverage(health, path)
        self.assertNotIn("B", coverage["missing_required_sources"])
        self.assertEqual(coverage["resolved_source_aliases"], {"B": "A"})
        self.assertTrue(coverage["acceptance_ready"])

    def test_successor_failure_propagates_to_alias(self):
        td, path = self._config({"B": "A"})
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "FAILED"}]
        coverage = manifest_coverage(health, path)
        self.assertIn("B", coverage["unhealthy_required_sources"])
        self.assertFalse(coverage["acceptance_ready"])

    def test_append_missing_health_emits_merged_source_row(self):
        td, path = self._config({"B": "A"})
        self.addCleanup(td.cleanup)
        health = [{"source": "A", "status": "LIVE", "lots_seen": 7, "scope_dates": ["2026-09-28"]}]
        append_missing_health(health, path)
        merged = next(x for x in health if x["source"] == "B")
        self.assertEqual(merged["status"], "MERGED SOURCE")
        self.assertEqual(merged["successor_source"], "A")
        self.assertEqual(merged["lots_seen"], 7)


if __name__ == "__main__":
    unittest.main()
