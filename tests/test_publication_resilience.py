import json
from datetime import date, datetime, timezone

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


def test_degraded_discovery_outage_retains_future_rows_without_claiming_freshness(tmp_path, monkeypatch):
    monkeypatch.setattr(publication_resilience, "manifest_coverage", lambda health: {"acceptance_ready": True})
    row = {"source":"Example Auctions", "url":"https://example.test/lot/1",
           "auction_date":"2026-10-13", "status":"STALE SOURCE"}
    path = _write(tmp_path, archive=[row,dict(row,url='https://example.test/lot/2',auction_date='2026-09-01')],
        health=[{"source":"Example Auctions", "status":"DEGRADED", "authoritative_snapshot":False,
                 "checked_at":"2026-10-06", "reconciliation":{"discovery_failures":["HTTP 403"]}}])
    data = publication_resilience.apply(path,today=date(2026,10,6))
    assert len(data['properties']) == 1 and len(data['archive']) == 1
    health = data['source_health'][0]
    assert health['status'] == 'DEGRADED' and not health['authoritative_snapshot']
    assert health['reconciliation']['discovery_failures'] == ['HTTP 403']
    assert data['integrity']['temporary_outage_sources_preserved'] == {'Example Auctions':1}


def test_rolling_undated_inventory_has_a_bounded_outage_window(tmp_path,monkeypatch):
    monkeypatch.setattr(publication_resilience,'manifest_coverage',lambda h:{'acceptance_ready':True})
    row={'source':'iamsold','url':'https://example.test/lot/recent','status':'STALE SOURCE',
         'collected_at':'2026-10-06T09:00:00+00:00'}
    path=_write(tmp_path,archive=[row,dict(row,url='https://example.test/lot/expired',collected_at='2026-10-03T09:00:00+00:00'),
        dict(row,url='https://example.test/lot/past-date',auction_date='2026-10-05')],
        health=[{'source':'iamsold','status':'FAILED','message':'temporary timeout'}])
    data=publication_resilience.apply(path,now=datetime(2026,10,6,12,tzinfo=timezone.utc))
    assert len(data['properties'])==1 and data['properties'][0]['url'].endswith('/recent')
    assert data['properties'][0]['collected_at']==row['collected_at']
    assert data['source_health'][0]['status']=='DEGRADED'
