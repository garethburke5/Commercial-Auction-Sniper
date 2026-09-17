import json
from datetime import date

from collectors import publication_resilience


def _write(tmp_path, *, properties=None, archive=None, health=None):
    path = tmp_path / "properties.json"
    path.write_text(json.dumps({
        "properties": properties or [],
        "archive": archive or [],
        "source_health": health or [],
    }), encoding="utf-8")
    return path


def test_failed_source_with_zero_inventory_becomes_degraded(tmp_path, monkeypatch):
    monkeypatch.setattr(publication_resilience, "manifest_coverage", lambda health: {"acceptance_ready": True})
    path = _write(tmp_path, health=[{
        "source": "Paul Fosh Auctions",
        "status": "FAILED",
        "message": "collector unavailable",
    }])

    data = publication_resilience.apply(path, today=date(2026, 9, 17))

    source = data["source_health"][0]
    assert source["status"] == "DEGRADED"
    assert source["authoritative_snapshot"] is False
    assert source["zero_inventory_outage"] is True
    assert data["integrity"]["zero_inventory_outage_sources"] == ["Paul Fosh Auctions"]
    assert data["integrity"]["acceptance_ready"] is True


def test_failed_source_preserves_future_stale_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(publication_resilience, "manifest_coverage", lambda health: {"acceptance_ready": True})
    path = _write(
        tmp_path,
        archive=[{
            "source": "Example Auctions",
            "url": "https://example.test/lot/1",
            "auction_date": "2026-09-20",
            "status": "STALE SOURCE",
        }],
        health=[{"source": "Example Auctions", "status": "FAILED", "message": "timeout"}],
    )

    data = publication_resilience.apply(path, today=date(2026, 9, 17))

    assert len(data["properties"]) == 1
    assert data["properties"][0]["status"] == "CURRENT"
    assert data["archive"] == []
    assert data["source_health"][0]["status"] == "DEGRADED"
    assert data["integrity"]["temporary_outage_sources_preserved"] == {"Example Auctions": 1}
    assert data["integrity"]["zero_inventory_outage_sources"] == []
