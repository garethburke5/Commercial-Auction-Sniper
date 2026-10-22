"""Independent freshness alarm: a blocked scan cannot leave stale stock unnoticed."""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


def check(snapshot, now=None, max_age_hours=14):
    now = now or datetime.now(timezone.utc)
    stamp = snapshot.get('generated_at')
    try:
        generated = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
        if generated.tzinfo is None:
            raise ValueError('timezone missing')
    except (TypeError, ValueError):
        return ['Collection timestamp is missing or invalid']
    errors = []
    if generated > now + timedelta(minutes=5):
        errors.append('Collection timestamp is in the future')
    if now - generated > timedelta(hours=max_age_hours):
        errors.append(f'Published collection is older than {max_age_hours} hours: {stamp}')
    if not snapshot.get('properties'):
        errors.append('Published catalogue has no properties')
    return errors


def check_sources(snapshot, now=None, max_age_hours=14):
    """An overall fresh snapshot must not conceal a failed individual source."""
    now = now or datetime.now(timezone.utc)
    errors = []
    for h in snapshot.get('source_health', []):
        if h.get('status') in ('MERGED SOURCE','NOT IMPLEMENTED') or not h.get('collector_executed'):
            continue
        name = h['source']
        if h.get('status') in ('FAILED','DEGRADED') or h.get('coverage_status') == 'DEGRADED':
            errors.append(name + ': ' + str(h.get('coverage_failure_reason') or h.get('message') or h['status']))
        stamp = h.get('last_successful_collection') or (h.get('checked_at') if h.get('status') == 'LIVE' else None)
        if stamp:
            try:
                parsed = datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if parsed.tzinfo is None: raise ValueError('missing timezone')
                if now - parsed > timedelta(hours=max_age_hours): errors.append(name + ': last successful collection overdue: ' + stamp)
                if parsed > now + timedelta(minutes=5): errors.append(name + ': invalid future collection timestamp')
            except (ValueError,TypeError): errors.append(name + ': invalid successful collection timestamp')
        elif h.get('status') not in ('CATALOGUE PENDING','NO CURRENT LOTS'):
            errors.append(name + ': no successful collection recorded')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', default='data/properties.json')
    parser.add_argument('--max-age-hours', type=float, default=14)
    parser.add_argument('--sources', action='store_true', help='Also fail on individual collection failures and stale sources')
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text())
    errors = check(snapshot, max_age_hours=args.max_age_hours)
    if args.sources: errors.extend(check_sources(snapshot, max_age_hours=args.max_age_hours))
    print(json.dumps({'generated_at': snapshot.get('generated_at'), 'healthy': not errors, 'errors': errors}))
    raise SystemExit(bool(errors))
