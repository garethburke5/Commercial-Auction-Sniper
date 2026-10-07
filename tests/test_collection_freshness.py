from datetime import datetime, timezone
from scripts.check_collection_freshness import check


def test_freshness_uses_real_collection_time_not_revalidation_time():
    now = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)
    data = {'generated_at': '2026-10-07T06:27:00Z', 'properties': [{}], 'integrity': {'revalidated_at': now.isoformat()}}
    assert not check(data, now)
    data['generated_at'] = '2026-10-06T06:27:00Z'
    assert 'older than' in check(data, now)[0]
    data['generated_at'] = '2026-10-08T06:27:00Z'
    assert 'future' in check(data, now)[0]


def test_unknown_timestamp_and_empty_stock_fail_closed():
    assert check({'properties': [{}]})
    assert check({'generated_at': datetime.now(timezone.utc).isoformat(), 'properties': []})
