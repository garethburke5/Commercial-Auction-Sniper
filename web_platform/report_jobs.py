"""Support recovery of interrupted reports without granting another entitlement."""
import json
import time

from fastapi import HTTPException
from .database import begin_write

STALE_SECONDS = 3600


def current(db, rid, attempt):
    row = db.execute('SELECT status,attempts FROM review_processing WHERE review_id=?', (rid,)).fetchone()
    return bool(row and row['status'] == 'processing' and row['attempts'] == attempt)


def recover(accounts, rid, attempt, owner, *, worker_stopped=False, now=None):
    """Owner confirms the old worker is stopped; elapsed time alone is not proof.

    The attempt number fences late results. Recovery neither runs a provider nor
    changes purchases, redemptions or the three-attempt limit.
    """
    from .accounts import require_owner
    require_owner(owner)
    if not worker_stopped:
        raise HTTPException(409, 'Confirm the previous worker has stopped and check provider activity before allowing a retry')
    now = int(time.time()) if now is None else now
    with accounts.db() as db:
        begin_write(db)
        job = db.execute('SELECT * FROM review_processing WHERE review_id=?', (rid,)).fetchone()
        record = db.execute('SELECT report_json FROM reviews WHERE id=?', (rid,)).fetchone()
        if not job or not record:
            raise HTTPException(404, 'Review not found')
        if not current(db, rid, attempt):
            raise HTTPException(409, 'The processing attempt has changed; refresh its status')
        if job['updated_at'] > now - STALE_SECONDS:
            raise HTTPException(409, 'This processing attempt is too recent for interrupted-job recovery')
        if attempt >= 3:
            raise HTTPException(409, 'The retry limit requires support review; recovery cannot reset it')
        ledger = db.execute('SELECT metrics_json FROM report_generation_attempts WHERE review_id=? AND attempt=?', (rid, attempt)).fetchone()
        if not ledger:
            raise HTTPException(409, 'The processing ledger needs support review')
        report = json.loads(record['report_json'])
        if report.get('analysis_state') in ('complete', 'requires_review'):
            raise HTTPException(409, 'A generated report cannot be reset through interrupted-job recovery')
        metrics = json.loads(ledger['metrics_json'] or '{}')
        metrics['recovery'] = {'at': now, 'owner': owner, 'worker_stopped_confirmed': True,
                               'usage_reconciliation_required': True}
        db.execute("UPDATE report_generation_attempts SET status='interrupted',finished_at=?,metrics_json=? WHERE review_id=? AND attempt=?",
                   (now, json.dumps(metrics), rid, attempt))
        db.execute("UPDATE review_processing SET status='failed',updated_at=? WHERE review_id=?", (now, rid))
        report['analysis_state'] = 'failed'
        db.execute('UPDATE reviews SET report_json=? WHERE id=?', (json.dumps(report), rid))
    return {'status': 'retry_available', 'review_id': rid, 'attempts_used': attempt,
            'message': 'Purchase retained. The customer may retry with their documents; no investigation has been restarted.'}
