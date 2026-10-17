"""Opt-in alert delivery on top of existing watch/search events.

Disabled by default. Provider acceptance is not proof of inbox delivery.
Retries reuse an immutable payload and stop before provider deduplication expires.
"""
import base64
import hmac
import hashlib
import json
import os
import re
import secrets
import time
import uuid
from html import escape
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from .database import begin_write
from .plans import ENTITLEMENTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_preferences(
 user_id TEXT PRIMARY KEY,auth_subject TEXT NOT NULL,email TEXT NOT NULL,enabled INTEGER NOT NULL,
 enabled_at BIGINT NOT NULL,unsubscribe_token TEXT NOT NULL UNIQUE,updated_at BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_outbox(
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL,payload_json TEXT NOT NULL,
 status TEXT NOT NULL,created_at BIGINT NOT NULL,first_attempt_at BIGINT,
 next_attempt_at BIGINT NOT NULL,lease_until BIGINT NOT NULL,lease_owner TEXT,
 attempts INTEGER NOT NULL DEFAULT 0,provider_id TEXT,last_error TEXT);
CREATE INDEX IF NOT EXISTS alert_outbox_due ON alert_outbox(status,next_attempt_at);
CREATE INDEX IF NOT EXISTS alert_outbox_user ON alert_outbox(user_id,created_at);
CREATE TABLE IF NOT EXISTS alert_outbox_events(
 event_key TEXT PRIMARY KEY,outbox_id TEXT NOT NULL,kind TEXT NOT NULL,source_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS alert_outbox_events_message ON alert_outbox_events(outbox_id);
CREATE TABLE IF NOT EXISTS alert_receipts(
 event_id TEXT PRIMARY KEY,provider_id TEXT NOT NULL,kind TEXT NOT NULL,received_at BIGINT NOT NULL);
CREATE INDEX IF NOT EXISTS alert_receipts_message ON alert_receipts(provider_id);
"""
ORIGIN = 'https://auctiongeek.co.uk'
RETRY_WINDOW = 23 * 3600  # Resend keeps idempotency keys for 24 hours.


def initialise(accounts):
    if not accounts.managed_schema:
        with accounts.db() as db:
            db.executescript(SCHEMA)


def configured():
    sender = os.getenv('ALERT_EMAIL_FROM', '')
    endpoint = os.getenv('ALERT_UNSUBSCRIBE_ORIGIN', '').rstrip('/')
    url = urlsplit(endpoint)
    return bool(os.getenv('ALERT_EMAIL_ENABLED') == 'true'
                and os.getenv('RESEND_API_KEY') and os.getenv('RESEND_WEBHOOK_SECRET', '').startswith('whsec_')
                and re.fullmatch(r'Auction Geek <[a-zA-Z0-9._+-]+@auctiongeek\.co\.uk>', sender)
                and url.scheme == 'https' and url.hostname
                and not url.username and not url.password and not url.query and not url.fragment
                and url.path in ('', '/'))


def verified_email(user, authorization, *, get=httpx.get):
    """Recipient comes from live Supabase Auth, never request body or metadata."""
    issuer = os.getenv('AUTH_ISSUER', '').rstrip('/')
    key = os.getenv('SUPABASE_PUBLISHABLE_KEY', '')
    if not issuer.startswith('https://') or not issuer.endswith('/auth/v1') or not key:
        raise HTTPException(503, 'Email verification is not configured')
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Sign in required')
    try:
        response = get(issuer + '/user', headers={'Authorization': authorization, 'apikey': key},
                       timeout=10, follow_redirects=False)
        response.raise_for_status()
        record = response.json()
        subject = record.get('id')
        email = record.get('email', '')
        valid = (isinstance(subject, str) and subject and record.get('email_confirmed_at')
                 and not record.get('is_anonymous') and isinstance(email, str)
                 and len(email) <= 254 and re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+', email)
                 and hashlib.sha256((issuer + '|' + subject).encode()).hexdigest() == user)
        if not valid:
            raise HTTPException(403, 'Confirm your account email before enabling alerts')
        return email, subject
    except (httpx.HTTPError, ValueError, TypeError):
        raise HTTPException(503, 'Could not verify your email; alerts have not been enabled')


def preferences(accounts, user):
    initialise(accounts)
    with accounts.db() as db:
        row = db.execute('SELECT enabled FROM alert_preferences WHERE user_id=?', (user,)).fetchone()
    return {'enabled': bool(row and row['enabled']), 'delivery_available': configured()}


def set_preferences(accounts, user, enabled, authorization=None, *, verify=verified_email):
    initialise(accounts)
    if enabled:
        accounts.require(user, 'alerts')
        if not configured():
            raise HTTPException(503, 'Email alerts are not yet available')
        email, subject = verify(user, authorization)
    else:
        email, subject = '', ''
    now = int(time.time())
    with accounts.db() as db:
        begin_write(db)
        previous = db.execute('SELECT * FROM alert_preferences WHERE user_id=?', (user,)).fetchone()
        if enabled and previous and previous['enabled'] and previous['email'] == email:
            return {'enabled': True, 'delivery_available': configured()}
        if enabled:
            for old in db.execute("SELECT payload_json FROM alert_outbox WHERE user_id=? AND status IN ('bounced','complained')", (user,)):
                if json.loads(old['payload_json'])['to'] == [email]:
                    raise HTTPException(409, 'Email alerts were stopped after a delivery problem. Contact support before re-enabling.')
        # Reset the time boundary on a new opt-in: no historical backlog emails.
        db.execute('''INSERT INTO alert_preferences VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id)
         DO UPDATE SET auth_subject=excluded.auth_subject,email=excluded.email,enabled=excluded.enabled,enabled_at=excluded.enabled_at,
         unsubscribe_token=excluded.unsubscribe_token,updated_at=excluded.updated_at''',
         (user, subject, email, int(enabled), now, secrets.token_urlsafe(32), now))
        db.execute("UPDATE alert_outbox SET status='suppressed' WHERE user_id=? AND status IN ('pending','sending')", (user,))
    return {'enabled': bool(enabled), 'delivery_available': configured()}


def unsubscribe(accounts, token):
    initialise(accounts)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{43}', token):
        raise HTTPException(404, 'Unsubscribe link not found')
    with accounts.db() as db:
        begin_write(db)
        pref = db.execute('SELECT user_id FROM alert_preferences WHERE unsubscribe_token=?', (token,)).fetchone()
        if not pref:
            raise HTTPException(404, 'Unsubscribe link not found')
        user = pref['user_id']
        db.execute('UPDATE alert_preferences SET enabled=0,email=?,updated_at=? WHERE user_id=?', ('', int(time.time()), user))
        db.execute("UPDATE alert_outbox SET status='suppressed' WHERE user_id=? AND status IN ('pending','sending')", (user,))
    return {'unsubscribed': True}


def message(email, token):
    # No private addresses, notes, search terms or investment details in email.
    # The account link still requires authentication and existing ownership checks.
    stop = os.environ['ALERT_UNSUBSCRIBE_ORIGIN'].rstrip('/') + '/api/alerts/unsubscribe/' + token
    link = ORIGIN + '/account/'
    text = ('Your Auction Geek updates are ready.\n\n'
            'A property you watch has changed, or a new property matches an enabled saved search. '
            'Sign in to review the latest source information before making a decision.\n\n'
            'View My Auction Geek: ' + link + '\n\n'
            'You received this because you enabled email alerts. Stop email alerts: ' + stop)
    html = ('<!doctype html><html lang="en"><body style="margin:0;background:#f6f7f7;color:#203932;font-family:Arial,sans-serif">'
            '<div style="max-width:560px;margin:24px auto;padding:28px;background:white">'
            '<p style="font-size:22px;font-weight:bold">Auction Geek</p>'
            '<h1 style="font-size:25px;line-height:1.25">Your property updates are ready</h1>'
            '<p style="line-height:1.6">A property you watch has changed, or a new property matches an enabled saved search.</p>'
            '<p style="line-height:1.6">Sign in to review the latest source information before making a decision.</p>'
            '<p style="margin:28px 0"><a style="display:inline-block;padding:14px 20px;background:#203932;color:white;text-decoration:none" href="'
            + link + '">View My Auction Geek</a></p>'
            '<p style="font-size:13px;line-height:1.6">You enabled email alerts. '
            '<a href="' + escape(stop, quote=True) + '">Stop email alerts</a>.</p></div></body></html>')
    return {'from': os.environ['ALERT_EMAIL_FROM'], 'to': [email],
            'subject': 'Your Auction Geek property updates', 'text': text, 'html': html,
            'headers': {'List-Unsubscribe': '<' + stop + '>',
                        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click'}}


def enqueue(accounts, *, now=None):
    """Queue existing events once; retain ownership and explicit search opt-in."""
    if not configured():
        return 0
    from .workspace import initialise as workspace_init
    workspace_init(accounts)
    initialise(accounts)
    now = int(time.time()) if now is None else now
    added = 0
    with accounts.db() as db:
        users = [dict(r) for r in db.execute('SELECT * FROM alert_preferences WHERE enabled=1')]
    for pref in users:
        user = pref['user_id']
        if 'alerts' not in ENTITLEMENTS[accounts.plan(user)]:
            continue
        with accounts.db() as db:
            begin_write(db)
            # Re-read preference under the shared lock to serialize unsubscribe.
            current = db.execute('SELECT * FROM alert_preferences WHERE user_id=?', (user,)).fetchone()
            if not current or not current['enabled'] or current['unsubscribe_token'] != pref['unsubscribe_token']:
                continue
            if db.execute('SELECT 1 FROM alert_outbox WHERE user_id=? AND created_at>? LIMIT 1', (user, now-86400)).fetchone():
                continue
            events = list(db.execute('''SELECT e.id,e.property_id AS source_id,'watch' AS kind FROM watch_events e
              JOIN workspace w ON w.user_id=e.user_id AND w.property_id=e.property_id
              WHERE e.user_id=? AND w.watched=1 AND e.created_at>? AND e.created_at>=?
              AND NOT EXISTS (SELECT 1 FROM alert_outbox_events o WHERE o.event_key='watch:' || e.id)
              ORDER BY e.created_at,e.id LIMIT 100''', (user, pref['enabled_at'], now-86400)))
            events += list(db.execute('''SELECT m.id,m.search_id AS source_id,'search' AS kind FROM search_matches m
              JOIN saved_searches s ON s.user_id=m.user_id AND s.search_id=m.search_id
              WHERE m.user_id=? AND s.digest=1 AND m.created_at>? AND m.created_at>=? AND m.created_at>s.created_at
              AND NOT EXISTS (SELECT 1 FROM alert_outbox_events o WHERE o.event_key='search:' || m.id)
              ORDER BY m.created_at,m.id LIMIT 100''', (user, pref['enabled_at'], now-86400)))
            if events:
                oid = uuid.uuid4().hex
                db.execute("""INSERT INTO alert_outbox
                 (id,user_id,payload_json,status,created_at,next_attempt_at,lease_until,attempts)
                 VALUES (?,?,?,'pending',?,?,0,0)""",
                 (oid, user, json.dumps(message(pref['email'], pref['unsubscribe_token'])), now, now))
                for event in events:
                    db.execute('INSERT INTO alert_outbox_events VALUES (?,?,?,?)',
                               (event['kind'] + ':' + event['id'], oid, event['kind'], event['source_id']))
                added += 1

    return added


def recipient(db, user):
    # A narrowly scoped private view exposes only confirmed, unbanned opted-in
    # recipients. No Auth credentials or broad auth.users grants reach the API.
    row = db.execute('SELECT email FROM alert_recipients WHERE user_id=?', (user,)).fetchone()
    return row['email'] if row else None


def eligible(db, row, lookup=recipient):
    pref = db.execute('SELECT enabled,email,unsubscribe_token FROM alert_preferences WHERE user_id=?', (row['user_id'],)).fetchone()
    payload = json.loads(row['payload_json'])
    if not pref or not pref['enabled'] or payload['to'] != [pref['email']]:
        return False
    if lookup(db, row['user_id']) != pref['email']:
        return False
    expected_stop = '/api/alerts/unsubscribe/' + pref['unsubscribe_token']
    if expected_stop not in payload['headers']['List-Unsubscribe']:
        return False
    for event in db.execute('SELECT kind,source_id FROM alert_outbox_events WHERE outbox_id=?', (row['id'],)):
        if event['kind'] == 'watch':
            if db.execute('SELECT 1 FROM workspace WHERE user_id=? AND property_id=? AND watched=1', (row['user_id'], event['source_id'])).fetchone():
                return True
        elif db.execute('SELECT 1 FROM saved_searches WHERE user_id=? AND search_id=? AND digest=1', (row['user_id'], event['source_id'])).fetchone():
            return True
    return False


def reconcile_receipts(db, provider_id):
    rows = list(db.execute('SELECT * FROM alert_outbox WHERE provider_id=?', (provider_id,)))
    kinds = {r[0] for r in db.execute('SELECT kind FROM alert_receipts WHERE provider_id=?', (provider_id,))}
    state = next((k for k in ('complained','bounced','suppressed','failed','delivered') if 'email.'+k in kinds), None)
    if not state:
        return
    for row in rows:
        db.execute('UPDATE alert_outbox SET status=?,lease_until=0 WHERE id=?', (state, row['id']))
        if state in ('complained','bounced','suppressed'):
            # A receipt for an older address must not disable a freshly verified
            # replacement address. Provider IDs remain attached for audit.
            address = json.loads(row['payload_json'])['to'][0]
            pref = db.execute('SELECT email FROM alert_preferences WHERE user_id=?', (row['user_id'],)).fetchone()
            if pref and pref['email'] == address:
                db.execute('UPDATE alert_preferences SET enabled=0,updated_at=? WHERE user_id=?', (int(time.time()), row['user_id']))
                db.execute("UPDATE alert_outbox SET status='suppressed' WHERE user_id=? AND status IN ('pending','sending')", (row['user_id'],))


def webhook(accounts, body, headers, *, now=None):
    secret = os.getenv('RESEND_WEBHOOK_SECRET','')
    if not secret.startswith('whsec_'):
        raise HTTPException(503, 'Delivery receipts are not configured')
    now = int(time.time()) if now is None else now
    event_id, stamp, signatures = (headers.get(k,'') for k in ('svix-id','svix-timestamp','svix-signature'))
    try:
        if len(body)>100000 or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',event_id) or abs(now-int(stamp))>300:
            raise ValueError()
        expected=base64.b64encode(hmac.new(base64.b64decode(secret[6:],validate=True),
            event_id.encode()+b'.'+stamp.encode()+b'.'+body,hashlib.sha256).digest()).decode()
        if not any(hmac.compare_digest(s,'v1,'+expected) for s in signatures.split()):raise ValueError()
        payload=json.loads(body)
        kind=payload.get('type')
        provider_id=payload.get('data',{}).get('email_id')
        if not isinstance(provider_id,str) or not 1<=len(provider_id)<=200:raise ValueError()
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(400,'Invalid delivery receipt')
    initialise(accounts)
    with accounts.db() as db:
        begin_write(db)
        if db.execute('SELECT 1 FROM alert_receipts WHERE event_id=?',(event_id,)).fetchone():
            return {'status':'duplicate'}
        if kind not in {'email.delivered','email.bounced','email.complained','email.failed','email.suppressed'}:
            return {'status':'ignored'}
        db.execute('INSERT INTO alert_receipts VALUES (?,?,?,?)',(event_id,provider_id,kind,now))
        reconcile_receipts(db,provider_id)
    return {'status':'recorded'}


def dispatch(accounts, *, post=httpx.post, now=None, limit=5, lookup=recipient):
    if not configured():
        return {'status': 'disabled', 'accepted': 0}
    initialise(accounts)
    now = int(time.time()) if now is None else now
    accepted = 0
    for _ in range(min(limit, 10)):
        owner = uuid.uuid4().hex
        with accounts.db() as db:
            begin_write(db)
            row = db.execute("""SELECT * FROM alert_outbox WHERE status IN ('pending','sending')
             AND next_attempt_at<=? AND lease_until<=? ORDER BY created_at,id LIMIT 1""", (now, now)).fetchone()
            if not row:
                break
            row = dict(row)
            if row['first_attempt_at'] is None and now-row['created_at']>=86400:
                db.execute("UPDATE alert_outbox SET status='suppressed',last_error='digest_expired' WHERE id=?",(row['id'],))
                continue
            if (row['first_attempt_at'] is not None and now-row['first_attempt_at'] >= RETRY_WINDOW):
                # Outcome may be unknown: never blindly resend after the provider window.
                db.execute("UPDATE alert_outbox SET status='needs_review',last_error='retry_window_expired' WHERE id=?", (row['id'],))
                continue
            if not eligible(db, row, lookup):
                db.execute("UPDATE alert_outbox SET status='suppressed' WHERE id=?", (row['id'],))
                continue
            recent=db.execute('SELECT MAX(first_attempt_at) FROM alert_outbox WHERE user_id=? AND id<>?', (row['user_id'],row['id'])).fetchone()[0]
            if row['first_attempt_at'] is None and recent is not None and recent+86400>now:
                db.execute('UPDATE alert_outbox SET next_attempt_at=? WHERE id=?',(recent+86400,row['id']))
                continue
            db.execute("""UPDATE alert_outbox SET status='sending',lease_owner=?,lease_until=?,
             first_attempt_at=COALESCE(first_attempt_at,?),attempts=attempts+1 WHERE id=?""", (owner, now+120, now, row['id']))
        with accounts.db() as db:
            allowed=eligible(db,row,lookup)
        # Recheck current billing and recipient immediately before the call.
        if not allowed or 'alerts' not in ENTITLEMENTS[accounts.plan(row['user_id'])]:
            state, error, provider = 'suppressed', 'membership_inactive', None
        else:
            try:
                response = post('https://api.resend.com/emails', json=json.loads(row['payload_json']),
                                headers={'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY'],
                                         'Idempotency-Key': 'auction-alert/' + row['id']},
                                timeout=15, follow_redirects=False)
                if response.status_code in (200, 201) and response.json().get('id'):
                    state, error, provider = 'accepted', None, str(response.json()['id'])
                    accepted += 1
                elif response.status_code == 429 or response.status_code >= 500:
                    state, error, provider = 'pending', 'provider_retryable', None
                else:
                    state, error, provider = 'needs_review', 'provider_rejected', None
            except (httpx.HTTPError, ValueError, TypeError):
                state, error, provider = 'pending', 'provider_outcome_unknown', None
        with accounts.db() as db:
            begin_write(db)
            # Keep a receipt correlation even if unsubscribe occurred in-flight.
            db.execute("""UPDATE alert_outbox SET
             status=CASE WHEN status='sending' THEN ? ELSE status END,
             lease_until=0,next_attempt_at=?,provider_id=COALESCE(?,provider_id),last_error=?
             WHERE id=? AND lease_owner=?""",
             (state, now+min(3600,60*2**min(row['attempts'],6)),provider,error,row['id'],owner))
            if provider:reconcile_receipts(db,provider)
    return {'status':'enabled','accepted':accepted}


def run(accounts):
    if not configured():return {'status':'disabled','accepted':0}
    queued=enqueue(accounts)
    return {'queued':queued,**dispatch(accounts)}


def status(accounts):
    if not configured():return {'status':'disabled','counts':{}}
    with accounts.db() as db:
        counts={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) AS n FROM alert_outbox GROUP BY status')}
    return {'status':'enabled','counts':counts}
