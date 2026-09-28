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

PLANS = {'free':frozenset({'save'}), 'investor':frozenset({'save','intelligence','alerts'}),
         'professional':frozenset({'save','intelligence','alerts','reports'}),
         'business':frozenset({'save','intelligence','alerts','reports','api'})}

class Accounts:
    def __init__(self, path):
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
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=20)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def ensure(self,user):
        with self.db() as db: db.execute('INSERT OR IGNORE INTO accounts(user_id) VALUES (?)',(user,))

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

    def purchases(self,user):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT order_id,product,property_id,status,created_at FROM purchases WHERE user_id=? ORDER BY created_at DESC',(user,))]

@lru_cache(maxsize=4)
def key_client(issuer):
    return jwt.PyJWKClient(issuer.rstrip('/')+'/.well-known/jwks.json',cache_jwk_set=True,lifespan=300)

def verify_token(token,issuer,audience='authenticated',client=None):
    key=(client or key_client(issuer)).get_signing_key_from_jwt(token).key
    claims=jwt.decode(token,key,algorithms=['RS256','ES256'],audience=audience,issuer=issuer,
                      options={'require':['exp','iat','iss','sub','aud']})
    if not isinstance(claims['sub'],str) or not claims['sub'] or claims.get('is_anonymous'):
        raise jwt.InvalidTokenError('Named account required')
    return hashlib.sha256((issuer+'|'+claims['sub']).encode()).hexdigest()

def authenticated_user(authorization):
    issuer=os.environ.get('AUTH_ISSUER','').rstrip('/')
    if not issuer.startswith('https://'): raise HTTPException(503,'Accounts are not enabled')
    if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Sign in required')
    try: return verify_token(authorization[7:],issuer)
    except (jwt.PyJWTError,ValueError): raise HTTPException(401,'Invalid or expired session')
