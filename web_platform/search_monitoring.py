"""Owner-scoped saved-search matches. Email delivery is deliberately separate."""
import json
import math
import re
import time
import unicodedata
import uuid
from datetime import datetime
from urllib.parse import parse_qs

from .board import search_text
from .database import begin_write
from .plans import ENTITLEMENTS


SCHEMA = '''
CREATE TABLE IF NOT EXISTS search_baselines(
 user_id TEXT NOT NULL,search_id TEXT NOT NULL,query TEXT NOT NULL,state_json TEXT NOT NULL,
 PRIMARY KEY(user_id,search_id));
CREATE TABLE IF NOT EXISTS search_matches(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,search_id TEXT NOT NULL,property_id TEXT NOT NULL,
 property_json TEXT NOT NULL,created_at BIGINT NOT NULL);
CREATE INDEX IF NOT EXISTS search_matches_account ON search_matches(user_id,search_id,created_at);
'''


def normalise(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = re.sub('[\u0300-\u036f]', '', text).lower().replace("'", '').replace('’', '')
    return re.sub('[^a-z0-9]+', ' ', text).strip()


def matches(row, query):
    """Same criteria as Find Property; sort order does not change membership."""
    params = parse_qs(query)
    first = lambda key: params.get(key, [''])[0]
    text = row.get('search_text')
    if text is None:
        text = search_text(row)
    if any(term not in text for term in normalise(first('q')).split()):
        return False
    sources = params.get('source', [])
    if sources and not set(sources).intersection([row.get('source'), *(row.get('source_brands') or [])]):
        return False
    if first('tenure') and str(row.get('tenure') or '').lower() != first('tenure').lower():
        return False
    if first('status') == 'available' and row.get('unavailable'):
        return False
    if first('status') == 'unavailable' and not row.get('unavailable'):
        return False
    for key, value in [('min', row.get('guide_price')), ('max', row.get('guide_price')),
                       ('yield', row.get('giy_min', row.get('giy')))]:
        raw = first(key).strip()
        try:
            limit = float(raw)
        except ValueError:
            continue
        if not math.isfinite(limit) or limit < 0:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            return False
        if (key == 'max' and value > limit) or (key != 'max' and value < limit):
            return False
    return True


def refresh_searches(accounts, user, rows, snapshot, *, now=None):
    """Baseline each healthy source, then record each newly qualifying lot once.

    Callers supply only current searchable catalogue rows, never the archive.
    Missing/degraded sources retain their baseline. Older concurrent snapshots
    cannot replace newer state. A first check establishes a baseline, not alerts.
    """
    from .monitoring import healthy_sources
    healthy = healthy_sources(snapshot, now=now)
    if not healthy or 'saved_searches' not in ENTITLEMENTS[accounts.plan(user)]:
        return 0
    stamp = datetime.fromisoformat(snapshot['generated_at'].replace('Z', '+00:00')).timestamp()
    grouped = {source: [] for source in healthy}
    for row in rows.values():
        if row.get('source') in grouped:
            grouped[row['source']].append(row)
    added = 0
    with accounts.db() as db:
        begin_write(db)
        searches = db.execute('SELECT search_id,query FROM saved_searches WHERE user_id=?', (user,)).fetchall()
        for search in searches:
            sid, query = search['search_id'], search['query']
            previous = db.execute('SELECT query,state_json FROM search_baselines WHERE user_id=? AND search_id=?', (user, sid)).fetchone()
            state = json.loads(previous['state_json']) if previous and previous['query'] == query else {}
            for source, candidates in grouped.items():
                prior = state.get(source)
                if prior and stamp <= prior['stamp']:
                    continue
                seen = set(prior['seen']) if prior else set()
                for row in candidates:
                    if not matches(row, query):
                        continue
                    pid = row['id']
                    if prior and pid not in seen:
                        safe = {key: row.get(key) for key in ('id', 'address', 'path', 'source', 'guide_price')}
                        db.execute('INSERT INTO search_matches VALUES (?,?,?,?,?,?)',
                                   (uuid.uuid4().hex, user, sid, pid, json.dumps(safe), int(time.time())))
                        added += 1
                    seen.add(pid)
                state[source] = {'stamp': stamp, 'seen': sorted(seen)}
            db.execute('''INSERT INTO search_baselines VALUES (?,?,?,?) ON CONFLICT(user_id,search_id)
                          DO UPDATE SET query=excluded.query,state_json=excluded.state_json''',
                       (user, sid, query, json.dumps(state)))
    return added


def clear_search_state(db, user, sid):
    for table in ('search_baselines', 'search_matches'):
        db.execute(f'DELETE FROM {table} WHERE user_id=? AND search_id=?', (user, sid))


def recent_matches(db, user, sid):
    return [{'property':json.loads(row['property_json']), 'created_at':row['created_at']} for row in db.execute(
        'SELECT property_json,created_at FROM search_matches WHERE user_id=? AND search_id=? ORDER BY created_at DESC,id DESC LIMIT 10',
        (user, sid))]
