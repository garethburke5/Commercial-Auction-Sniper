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


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', default='data/properties.json')
    parser.add_argument('--max-age-hours', type=float, default=14)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text())
    errors = check(snapshot, max_age_hours=args.max_age_hours)
    print(json.dumps({'generated_at': snapshot.get('generated_at'), 'healthy': not errors, 'errors': errors}))
    raise SystemExit(bool(errors))
