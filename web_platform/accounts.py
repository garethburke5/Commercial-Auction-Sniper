"""Managed identity boundary and private account storage; no passwords or cards.

Supabase Auth (asymmetric signing keys) owns registration, recovery and sessions.
Only server-verified access tokens reach this store. Roles are never read from
user-editable metadata. No account service is enabled without explicit config.
"""
import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
import jwt
from fastapi import HTTPException

from .plans import ENTITLEMENTS as PLANS

def is_owner(user_id):
    return user_id in {x.strip() for x in os.getenv('ADMIN_ACCOUNT_IDS','').split(',') if x.strip()}

def require_owner(user_id):
    if not is_owner(user_id):
        raise HTTPException(403,'Owner access required')

class Accounts:
    def __init__(self, path=None, *, database_url=None):
        self.database_url=database_url
        self.managed_schema=bool(database_url)
        if self.managed_schema:
            self.path=None
            with self.db() as db:
                version=db.execute('SELECT version FROM schema_version WHERE id=1').fetchone()
                if not version or version['version']!=1:
                    raise RuntimeError('Private account database migration is required')
                db.execute('SELECT 1 FROM report_credit_periods LIMIT 1')
                db.execute('SELECT 1 FROM report_rejections LIMIT 0')
                db.execute('SELECT 1 FROM report_credit_returns LIMIT 0')
                db.execute('SELECT 1 FROM report_refunds LIMIT 0')
                db.execute('SELECT 1 FROM active_account_sessions LIMIT 0')
            return
        if not path:
            raise ValueError('A private database URL or persistent SQLite path is required')
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS accounts(user_id TEXT PRIMARY KEY,customer_id TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS saved(user_id TEXT NOT NULL,property_id TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(user_id,property_id));
            CREATE TABLE IF NOT EXISTS subscriptions(subscription_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,plan TEXT NOT NULL,status TEXT NOT NULL,valid_until INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS webhook_events(event_id TEXT PRIMARY KEY,processed_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS purchases(order_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,product TEXT NOT NULL,property_id TEXT NOT NULL,price_id TEXT NOT NULL,session_id TEXT UNIQUE,payment_intent TEXT,status TEXT NOT NULL,created_at INTEGER NOT NULL);
            ''')
        from .report_credits import SCHEMA
        with self.db() as db:db.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        if self.managed_schema:
            from .database import connect_postgres,PostgresConnection
            with connect_postgres(self.database_url) as db:
                db.execute('SET LOCAL search_path TO auction_private, pg_catalog')
                db.execute("SET LOCAL statement_timeout = '30s'")
                db.execute("SET LOCAL lock_timeout = '10s'")
                yield PostgresConnection(db)
            return
        db=sqlite3.connect(self.path,timeout=20)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def ensure(self,user):
        with self.db() as db: db.execute('INSERT INTO accounts(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING',(user,))

    def customer(self,user):
        with self.db() as db:
            row=db.execute('SELECT customer_id FROM accounts WHERE user_id=?',(user,)).fetchone()
            return row['customer_id'] if row else None

    def plan(self,user):
        with self.db() as db:
            rows=db.execute("SELECT plan FROM subscriptions WHERE user_id=? AND status IN ('active','trialing') AND valid_until>?",(user,int(time.time()))).fetchall()
        return max((r['plan'] for r in rows if r['plan'] in PLANS),key=lambda x:len(PLANS[x]),default='free')

    def require(self,user,feature):
        if feature not in PLANS[self.plan(user)]: raise HTTPException(403,'Subscription does not include this feature')

    def billing_status(self,user):
        """Customer-safe billing state; this never grants membership access."""
        with self.db() as db:
            account=db.execute('SELECT customer_id FROM accounts WHERE user_id=?',(user,)).fetchone()
            rows=db.execute('SELECT plan,status,valid_until FROM subscriptions WHERE user_id=? ORDER BY valid_until DESC',(user,)).fetchall()
        rows=[dict(r) for r in rows if r['plan'] in PLANS and r['plan']!='free']
        now=int(time.time())
        active=next((r for r in rows if r['status'] in ('active','trialing') and r['valid_until']>now),None)
        pending=next((r for r in rows if r['status'] in ('past_due','unpaid','incomplete')),None)
        current=active or pending or next(iter(rows),None)
        status=current['status'] if current else 'none'
        return {'status':status,'plan':current['plan'] if current else 'free',
                'has_customer':bool(account and account['customer_id']),
                'payment_required':not active and status in ('past_due','unpaid','incomplete')}

    def purchases(self,user):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT order_id,product,property_id,status,created_at FROM purchases WHERE user_id=? ORDER BY created_at DESC',(user,))]

@lru_cache(maxsize=4)
def key_client(issuer):
    return jwt.PyJWKClient(issuer.rstrip('/')+'/.well-known/jwks.json',cache_jwk_set=True,lifespan=300)

def verify_token(token,issuer,audience='authenticated',client=None,session_check=None):
    key=(client or key_client(issuer)).get_signing_key_from_jwt(token).key
    claims=jwt.decode(token,key,algorithms=['RS256','ES256'],audience=audience,issuer=issuer,
                      options={'require':['exp','iat','iss','sub','aud']})
    if not isinstance(claims['sub'],str) or not claims['sub'] or claims.get('is_anonymous'):
        raise jwt.InvalidTokenError('Named account required')
    if session_check is not None:
        session_check(claims)
    return hashlib.sha256((issuer+'|'+claims['sub']).encode()).hexdigest()

def require_current_session(claims):
    """A signed JWT alone remains valid after Supabase revokes its session.

    Check only the private, read-only projection; never expose Auth records or
    cache acceptance across requests. Public browsing does not use this path.
    """
    from uuid import UUID
    from .database import connect_postgres
    try:
        subject=str(UUID(claims['sub']))
        session=str(UUID(claims['session_id']))
    except (KeyError,ValueError,TypeError,AttributeError):
        raise jwt.InvalidTokenError('Named session required')
    dsn=os.getenv('ACCOUNT_DATABASE_URL')
    if not dsn:
        raise HTTPException(503,'Session verification is not configured')
    try:
        with connect_postgres(dsn) as db:
            db.execute("SET LOCAL statement_timeout = '5s'")
            row=db.execute('SELECT 1 FROM auction_private.active_account_sessions WHERE session_id=%s AND auth_subject=%s',
                           (session,subject)).fetchone()
    except Exception:
        # Fail closed without returning database details, connection strings or
        # token claims. An outage is not a reason to accept a revoked session.
        raise HTTPException(503,'Could not verify your session; please try again') from None
    if not row:
        raise jwt.InvalidTokenError('Inactive session')

def authenticated_user(authorization):
    issuer=os.environ.get('AUTH_ISSUER','').rstrip('/')
    if not issuer.startswith('https://'): raise HTTPException(503,'Accounts are not enabled')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Sign in required')
    try: return verify_token(authorization[7:],issuer,session_check=require_current_session)
    except (jwt.PyJWTError,ValueError): raise HTTPException(401,'Invalid or expired session')
