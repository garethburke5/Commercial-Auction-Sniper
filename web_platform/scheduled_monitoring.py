"""Signed scheduler entrypoint; runs the existing private monitoring worker."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
from datetime import datetime

import httpx
from fastapi import HTTPException
from .database import begin_write

SOURCE_URL = 'https://raw.githubusercontent.com/garethburke5/Commercial-Auction-Sniper/main/data/properties.json'
MAX_BYTES = 25_000_000
SCHEMA = '''CREATE TABLE IF NOT EXISTS monitoring_jobs(
 name TEXT PRIMARY KEY,lease_owner TEXT NOT NULL,lease_until BIGINT NOT NULL,
 started_at BIGINT NOT NULL,finished_at BIGINT,status TEXT NOT NULL,details_json TEXT NOT NULL);'''


def signature(secret, stamp):
    message = f'{stamp}\nPOST\n/api/internal/monitor'.encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def authenticate(stamp, signed, *, now=None):
    secret = os.getenv('MONITORING_SIGNING_KEY', '')
    if len(secret) < 32:
        raise HTTPException(503, 'Scheduled monitoring is not configured')
    if not re.fullmatch(r'[0-9]{10}', stamp or '') or not re.fullmatch(r'[0-9a-f]{64}', signed or ''):
        raise HTTPException(401, 'Invalid scheduler signature')
    if abs((time.time() if now is None else now) - int(stamp)) > 300:
        raise HTTPException(401, 'Expired scheduler signature')
    if not hmac.compare_digest(signature(secret, stamp), signed):
        raise HTTPException(401, 'Invalid scheduler signature')


def download_snapshot():
    # Fixed first-party repository path: callers cannot supply an arbitrary URL.
    chunks, size = [], 0
    with httpx.stream('GET', SOURCE_URL, timeout=45, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('Published snapshot exceeds monitoring size limit')
            chunks.append(chunk)
    return json.loads(b''.join(chunks))


def timestamp(snapshot):
    return datetime.fromisoformat(snapshot['generated_at'].replace('Z', '+00:00')).timestamp()


def install_snapshot(root, snapshot):
    from scripts.check_collection_freshness import check
    from collectors.publication_quality import validate_publication
    from .catalogue import Catalogue
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('properties'), list):
        raise ValueError('Invalid published snapshot')
    if errors := check(snapshot):
        raise ValueError('; '.join(errors))
    if not isinstance(snapshot.get('source_health'), list) or not snapshot['source_health']:
        raise ValueError('Source health evidence is missing')
    if not isinstance(snapshot.get('archive', []), list):
        raise ValueError('Invalid archive contract')
    validate_publication(snapshot)
    path = Path(root) / 'data/properties.json'
    old = json.loads(path.read_text())
    if timestamp(snapshot) <= timestamp(old):
        return False
    # Validate the catalogue before replacing the shared file. Account requests
    # see either the complete old snapshot or the complete new one.
    with tempfile.TemporaryDirectory() as temp:
        test_root = Path(temp)
        (test_root/'data/auction_history').mkdir(parents=True)
        (test_root/'data/auction_history/progress.json').write_text('{}')
        (test_root/'data/properties.json').write_text(json.dumps(snapshot))
        candidate = Catalogue(test_root, summaries=False)
        candidate.close()
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
            pending = Path(output.name)
            json.dump(snapshot, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(pending, path)
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
    return True


def run(accounts, root, catalogue, *, fetch=download_snapshot, now=None):
    from .workspace import initialise
    from .monitoring import refresh
    initialise(accounts)
    now = int(time.time()) if now is None else now
    owner = uuid.uuid4().hex
    with accounts.db() as db:
        begin_write(db)
        job = db.execute("SELECT * FROM monitoring_jobs WHERE name='catalogue'").fetchone()
        if job and (job['lease_until'] > now or
                    (job['status'] == 'completed' and job['finished_at'] > now-600)):
            return {'status': 'already_checked_or_running'}
        db.execute('''INSERT INTO monitoring_jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(name)
                      DO UPDATE SET lease_owner=excluded.lease_owner,lease_until=excluded.lease_until,
                      started_at=excluded.started_at,finished_at=NULL,status=excluded.status,details_json=excluded.details_json''',
                   ('catalogue', owner, now+900, now, None, 'running', '{}'))
    try:
        changed = install_snapshot(root, fetch())
        current = catalogue()
        result = refresh(accounts, current.rows, current.snapshot,
                         search_rows={row['id']:row for row in current.properties})
        result.update(snapshot_updated=changed, generated_at=current.generated_at)
        status = 'completed'
    except Exception as error:
        # No raw provider responses, URLs, private rows or credentials in logs.
        result = {'error_type':type(error).__name__}
        status = 'failed'
    with accounts.db() as db:
        db.execute('''UPDATE monitoring_jobs SET lease_until=0,finished_at=?,status=?,details_json=?
                      WHERE name='catalogue' AND lease_owner=?''',
                   (int(time.time()), status, json.dumps(result), owner))
    if status == 'failed':
        raise HTTPException(503, 'Monitoring check failed; retained earlier observations')
    return {'status': 'completed'}


def status(accounts):
    from .workspace import initialise
    initialise(accounts)
    with accounts.db() as db:
        row = db.execute("SELECT started_at,finished_at,status,details_json FROM monitoring_jobs WHERE name='catalogue'").fetchone()
    if not row:
        return {'status':'not_run'}
    return {key:row[key] for key in ('started_at','finished_at','status')} | {'details':json.loads(row['details_json'])}
