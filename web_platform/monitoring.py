"""Private-host watch worker. Records account events; does not send email."""
import argparse
import json
import os
from pathlib import Path
from scripts.check_collection_freshness import check
from .accounts import Accounts
from .workspace import initialise, dashboard
from .plans import ENTITLEMENTS


def refresh(accounts, rows, snapshot, now=None):
    if errors := check(snapshot, now=now):
        raise ValueError('; '.join(errors))
    healthy = {h['source'] for h in snapshot.get('source_health', [])
               if h.get('status') == 'LIVE' and h.get('coverage_status') != 'DEGRADED'}
    trustworthy = {pid: row for pid, row in rows.items() if row.get('source') in healthy}
    initialise(accounts)
    with accounts.db() as db:
        users = [r[0] for r in db.execute('SELECT DISTINCT user_id FROM workspace WHERE watched=1')]
        before = db.execute('SELECT COUNT(*) FROM watch_events').fetchone()[0]
    processed = 0
    for user in users:
        if 'watch' not in ENTITLEMENTS[accounts.plan(user)]:
            continue
        dashboard(accounts, user, trustworthy)
        processed += 1
    with accounts.db() as db:
        after = db.execute('SELECT COUNT(*) FROM watch_events').fetchone()[0]
    return {'accounts_processed': processed, 'events_added': after-before,
            'healthy_sources': len(healthy), 'rows_withheld': len(rows)-len(trustworthy),
            'email_delivery': 'not enabled'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    database = os.environ.get('ACCOUNT_DATABASE_PATH')
    if not database:
        raise SystemExit('ACCOUNT_DATABASE_PATH must point to the private persistent database')
    snapshot = json.loads((args.root/'data/properties.json').read_text())
    if errors := check(snapshot):
        raise SystemExit('; '.join(errors))
    from .catalogue import Catalogue
    catalogue = Catalogue(args.root)
    try:
        print(json.dumps(refresh(Accounts(database), catalogue.rows, snapshot)))
    finally:
        catalogue.close()


if __name__ == '__main__':
    main()
