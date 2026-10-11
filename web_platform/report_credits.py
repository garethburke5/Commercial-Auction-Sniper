"""Invoice-funded monthly allowances. Every claim is bound to one owned report.

The same transaction lock is used by billing and processing. Periods never roll
over; changing a plan cannot reset usage or mint a second allowance mid-month.
Completed redemptions survive subscription expiry, but not a funding refund.
"""
import time
from fastapi import HTTPException
from .database import begin_write
from .plans import CATALOGUE

SCHEMA = '''
CREATE TABLE IF NOT EXISTS report_credit_periods(
 subscription_id TEXT NOT NULL,period_start BIGINT NOT NULL,period_end BIGINT NOT NULL,
 user_id TEXT NOT NULL,plan TEXT NOT NULL,allowance INTEGER NOT NULL CHECK(allowance>=0),
 invoice_id TEXT NOT NULL UNIQUE,status TEXT NOT NULL,
 PRIMARY KEY(subscription_id,period_start));
CREATE TABLE IF NOT EXISTS report_credit_payments(
 invoice_id TEXT NOT NULL,payment_intent TEXT NOT NULL,PRIMARY KEY(invoice_id,payment_intent));
CREATE TABLE IF NOT EXISTS report_credit_redemptions(
 review_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,subscription_id TEXT NOT NULL,
 period_start BIGINT NOT NULL,created_at BIGINT NOT NULL);
CREATE INDEX IF NOT EXISTS report_credit_usage ON report_credit_redemptions(subscription_id,period_start);
CREATE TABLE IF NOT EXISTS report_generation_attempts(
 review_id TEXT NOT NULL,attempt INTEGER NOT NULL,user_id TEXT NOT NULL,
 started_at BIGINT NOT NULL,finished_at BIGINT,status TEXT NOT NULL,
 upload_bytes BIGINT NOT NULL,upload_files INTEGER NOT NULL,metrics_json TEXT,
 PRIMARY KEY(review_id,attempt));
'''


def allowance(plan):
    return CATALOGUE.get(plan, {}).get('included_reports', 0)


def current_period(db, user, now):
    rows=db.execute('''SELECT p.*,s.plan AS current_plan FROM report_credit_periods p
        JOIN subscriptions s ON s.subscription_id=p.subscription_id AND s.user_id=p.user_id
        WHERE p.user_id=? AND p.status='paid' AND s.status='active'
          AND p.period_start<=? AND p.period_end>? AND s.valid_until>?
        ORDER BY p.period_start DESC''',(user,now,now,now)).fetchall()
    # Multiple subscriptions never combine their credits. Highest remaining
    # allowance is selected, with a stable subscription-id tie break.
    choices=[]
    for row in rows:
        p=dict(row);p['allowance']=min(p['allowance'],allowance(p['current_plan']))
        p['used']=db.execute('''SELECT COUNT(*) FROM report_credit_redemptions
            WHERE user_id=? AND created_at>=? AND created_at<?''',
            (user,p['period_start'],p['period_end'])).fetchone()[0]
        p['remaining']=max(0,p['allowance']-p['used']);choices.append(p)
    return max(choices,key=lambda p:(p['remaining'],p['period_start'],p['subscription_id']),default=None)


def balance(accounts,user):
    with accounts.db() as db:p=current_period(db,user,int(time.time()))
    return ({k:p[k] for k in ('allowance','used','remaining','period_start','period_end')} if p
            else {'allowance':0,'used':0,'remaining':0,'period_start':None,'period_end':None})


def credit_access(db,user,rid):
    return bool(db.execute('''SELECT 1 FROM report_credit_redemptions r
        JOIN report_credit_periods p ON p.subscription_id=r.subscription_id AND p.period_start=r.period_start
        WHERE r.user_id=? AND r.review_id=? AND p.user_id=? AND p.status='paid' ''',(user,rid,user)).fetchone())


def report_access(db,user,rid):
    return credit_access(db,user,rid) or bool(db.execute("SELECT 1 FROM purchases WHERE user_id=? AND product='legal_pack_report' AND property_id=? AND status='paid_awaiting_fulfilment'",(user,'review:'+rid)).fetchone())


def redeem(accounts,user,rid):
    from acquisition_quality import paid_report_status
    with accounts.db() as db:
        begin_write(db)
        report=db.execute('SELECT id FROM reviews WHERE id=? AND user_id=?',(rid,user)).fetchone()
        if not report:raise HTTPException(404,'Report not found')
        if credit_access(db,user,rid):return {'already_unlocked':True}
        if db.execute("SELECT 1 FROM purchases WHERE user_id=? AND product='legal_pack_report' AND property_id=? AND status='paid_awaiting_fulfilment'",(user,'review:'+rid)).fetchone():
            return {'already_unlocked':True}
        quality=paid_report_status()
        if not quality['purchase_available']:raise HTTPException(503,quality['message'])
        # An unresolved payment must not race credit redemption and charge twice.
        if db.execute("SELECT 1 FROM purchases WHERE user_id=? AND product='legal_pack_report' AND property_id=? AND status IN ('pending','refund_review','payment_review')",(user,'review:'+rid)).fetchone():
            raise HTTPException(409,'Resolve the existing report payment before using a credit')
        if db.execute('SELECT 1 FROM report_credit_redemptions WHERE review_id=?',(rid,)).fetchone():
            raise HTTPException(409,'This report credit requires payment review')
        now=int(time.time());p=current_period(db,user,now)
        if not p or not p['remaining']:raise HTTPException(402,'No included report credits remain for this billing month')
        db.execute('INSERT INTO report_credit_redemptions VALUES (?,?,?,?,?)',
                   (rid,user,p['subscription_id'],p['period_start'],now))
    return {'already_unlocked':False,'redeemed':True}
