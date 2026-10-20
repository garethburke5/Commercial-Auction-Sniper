"""Private history entitlements. Redirects, browser state and metadata grant nothing."""
import hashlib
import json
import os
import time
from fastapi import HTTPException
from .plans import CATALOGUE
from .market_context import address_key, postcode

PRODUCTS = frozenset({'property_history', 'history_day_pass', 'history_supporter_pass'})
SCHEMA = '''
CREATE TABLE IF NOT EXISTS history_order_terms(
 order_id TEXT PRIMARY KEY REFERENCES purchases(order_id),
 subject_key TEXT NOT NULL, amount_pence INTEGER NOT NULL,
 duration_seconds INTEGER NOT NULL, terms_version TEXT NOT NULL,
 paid_at INTEGER, expires_at INTEGER, currency TEXT,
 total_pence INTEGER, tax_pence INTEGER, receipt_url TEXT
);
'''

def subject_key(row):
    # An address alone must not join different freehold/leasehold interests.
    # No fuzzy matching or customer-supplied identifiers in the access boundary.
    if not postcode(row.get('address')) or not row.get('tenure'):
        return None
    subject = [address_key(row['address']), address_key(row['tenure'])]
    return hashlib.sha256(json.dumps(subject).encode()).hexdigest()

def offers():
    return CATALOGUE['history_products']

def sales_ready():
    return all(os.getenv(key) == 'true' for key in
               ('HISTORY_SALES_ENABLED', 'HISTORY_ARCHIVE_PRIVATE', 'HISTORY_QUALITY_APPROVED'))

def access(accounts, user, row, *, now=None, db=None):
    now = int(time.time()) if now is None else now
    key = subject_key(row)
    def check(con):
        membership = con.execute("SELECT plan FROM subscriptions WHERE user_id=? AND status IN ('active','trialing') AND valid_until>?", (user,now)).fetchall()
        if any(r['plan'] in ('investor','professional','business') for r in membership):
            return {'allowed':True, 'kind':'subscription', 'expires_at':None}
        grants = con.execute('''SELECT p.product,t.subject_key,t.expires_at FROM purchases p
            JOIN history_order_terms t ON t.order_id=p.order_id
            WHERE p.user_id=? AND p.status='paid_awaiting_fulfilment' AND t.paid_at IS NOT NULL''', (user,)).fetchall()
        for grant in grants:
            if grant['product']=='property_history' and key and grant['subject_key']==key:
                return {'allowed':True,'kind':'property_history','expires_at':None}
            if grant['product'] in ('history_day_pass','history_supporter_pass') and (grant['expires_at'] or 0)>now:
                return {'allowed':True,'kind':grant['product'],'expires_at':grant['expires_at']}
        return {'allowed':False,'kind':None,'expires_at':None}
    if db is not None:return check(db)
    with accounts.db() as con:return check(con)

def preview(context):
    """Only aggregate existence information crosses the public build boundary."""
    return {'previous_appearances':len(context.get('history') or []),
            'has_changes':bool(context.get('observations')),
            'has_comparables':bool(context.get('comparables'))}

def require_access(accounts,user,row):
    result=access(accounts,user,row)
    if not result['allowed']:raise HTTPException(403,'Premium history access is required')
    return result
