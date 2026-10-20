"""Settle rejected customer reports without deleting their funding audit trail.

Rejection and credit return commit with the generated result. Cash refunds use
a durable outbox: a provider/network failure cannot lose the customer's claim.
"""
import time
from .database import begin_write

SCHEMA = '''
CREATE TABLE IF NOT EXISTS report_rejections(
 review_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created_at BIGINT NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS report_credit_returns(
 review_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created_at BIGINT NOT NULL,
 replacement_review_id TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS report_refunds(
 order_id TEXT PRIMARY KEY,review_id TEXT NOT NULL,user_id TEXT NOT NULL,
 status TEXT NOT NULL,refund_id TEXT,updated_at BIGINT NOT NULL);
CREATE INDEX IF NOT EXISTS report_refunds_due ON report_refunds(status,updated_at);
'''


def reject(db, user, rid, report, reason='quality_rejected'):
    """Called under the processing transaction lock, after attempt fencing.

An included pack update carries no new charge: rejecting it must not refund
or revoke the already delivered original report. Private validation is unpaid.
"""
    if report.get('_validation'):
        return
    now = int(time.time())
    db.execute('INSERT INTO report_rejections VALUES (?,?,?,?) ON CONFLICT DO NOTHING',
               (rid, user, now, reason))
    if report.get('_intake', {}).get('parent_review_id'):
        return
    redemption = db.execute('SELECT 1 FROM report_credit_redemptions WHERE review_id=? AND user_id=?',
                            (rid, user)).fetchone()
    if redemption:
        db.execute('INSERT INTO report_credit_returns VALUES (?,?,?,NULL) ON CONFLICT DO NOTHING',
                   (rid, user, now))
    orders = db.execute("""SELECT order_id,status FROM purchases WHERE user_id=?
        AND product='legal_pack_report' AND property_id=?
        AND status IN ('paid_awaiting_fulfilment','quality_refund_pending')""", (user, 'review:'+rid)).fetchall()
    for order in orders:
        db.execute('INSERT INTO report_refunds VALUES (?,?,?,?,NULL,?) ON CONFLICT DO NOTHING',
                   (order['order_id'], rid, user, 'pending', now))
        db.execute("UPDATE purchases SET status='quality_refund_pending' WHERE order_id=?", (order['order_id'],))


def returned_credits(db, user):
    return db.execute('''SELECT c.review_id,r.subscription_id,r.period_start FROM report_credit_returns c
        JOIN report_credit_redemptions r ON r.review_id=c.review_id AND r.user_id=c.user_id
        JOIN report_credit_periods p ON p.subscription_id=r.subscription_id AND p.period_start=r.period_start
        WHERE c.user_id=? AND p.user_id=? AND p.status='paid' AND c.replacement_review_id IS NULL
        ORDER BY c.created_at,c.review_id''', (user, user)).fetchall()


def status(db, user, rid):
    rejection = db.execute('SELECT reason FROM report_rejections WHERE review_id=? AND user_id=?', (rid, user)).fetchone()
    if not rejection:
        return None
    credit = db.execute('SELECT replacement_review_id FROM report_credit_returns WHERE review_id=? AND user_id=?', (rid, user)).fetchone()
    refunds = db.execute('SELECT status FROM report_refunds WHERE review_id=? AND user_id=?', (rid, user)).fetchall()
    message = 'We could not produce a report that meets our quality standard.'
    if credit:
        eligible = any(c['review_id'] == rid for c in returned_credits(db, user))
        message += (' Your report credit has been returned and is available for another property.' if eligible else
                    ' Your returned report credit has already been used.' if credit['replacement_review_id'] else
                    ' Your credit is recorded, but its original payment needs review before it can be used.')
    if refunds:
        message += (' Your report payment has been refunded.' if all(r['status'] == 'succeeded' for r in refunds) else
                    ' Your report refund needs payment review.' if any(r['status'] == 'payment_review' for r in refunds) else
                    ' Your report refund is pending. You do not need to pay again.')
    if not credit and not refunds:
        message += ' No additional report charge or credit has been taken for this result.'
    return {'reason': rejection['reason'], 'credit_returned': bool(credit),
            'refund_status': [r['status'] for r in refunds], 'message': message}


def refund_order(billing, order_id):
    """Retry safely; verify current Stripe state and keep refund progress durable.

The same payment lock serialises this with webhook/credit settlement. Stripe's
idempotency key and a metadata lookup also cover a crash after remote success.
"""
    from .billing import plain
    billing.configured()
    with billing.accounts.db() as db:
        begin_write(db)
        queued = db.execute('SELECT * FROM report_refunds WHERE order_id=?', (order_id,)).fetchone()
        if not queued or queued['status'] == 'succeeded':
            return
        order = db.execute('SELECT * FROM purchases WHERE order_id=?', (order_id,)).fetchone()
        if not order or not order['payment_intent'] or not order['session_id']:
            db.execute("UPDATE report_refunds SET status='payment_review',updated_at=? WHERE order_id=?", (int(time.time()), order_id))
            return
        session = plain(billing.client.v1.checkout.sessions.retrieve(order['session_id']))
        intent = plain(billing.client.v1.payment_intents.retrieve(order['payment_intent'], {'expand': ['latest_charge']}))
        charge = intent.get('latest_charge') or {}
        if isinstance(charge, str):
            charge = plain(billing.client.v1.charges.retrieve(charge))
        customer = db.execute('SELECT customer_id FROM accounts WHERE user_id=?', (order['user_id'],)).fetchone()
        session_intent = session.get('payment_intent')
        if isinstance(session_intent, dict):
            session_intent = session_intent.get('id')
        valid = (customer and customer['customer_id'] and session.get('customer') == customer['customer_id']
                 and intent.get('customer') == customer['customer_id']
                 and session.get('client_reference_id') == order['user_id']
                 and session.get('metadata', {}).get('order_id') == order_id
                 and session_intent == order['payment_intent'] and session.get('mode') == 'payment'
                 and session.get('payment_status') == 'paid' and intent.get('status') == 'succeeded'
                 and charge.get('payment_intent') == order['payment_intent']
                 and charge.get('currency') == 'gbp' and not charge.get('disputed'))
        if not valid:
            db.execute("UPDATE report_refunds SET status='payment_review',updated_at=? WHERE order_id=?", (int(time.time()), order_id))
            return
        if queued['refund_id']:
            refund = plain(billing.client.v1.refunds.retrieve(queued['refund_id']))
        else:
            # Retrieve all refunds; never interpret the first page as complete.
            matches = []; all_refunds = []; params = {'payment_intent': order['payment_intent'], 'limit': 100}
            while True:
                page = plain(billing.client.v1.refunds.list(params))
                all_refunds.extend(page['data'])
                matches.extend(r for r in page['data'] if r.get('metadata', {}).get('report_order_id') == order_id)
                if not page.get('has_more'):
                    break
                if not page['data']:
                    raise RuntimeError('Incomplete refund reconciliation')
                params['starting_after'] = page['data'][-1]['id']
            if matches:
                refund = matches[0]
            elif charge.get('refunded'):
                # A fully allocated refund can still be pending at the bank.
                refund = {'status': 'succeeded' if all_refunds and all(r.get('status')=='succeeded' for r in all_refunds) else 'pending', 'id': None}
            else:
                refund = plain(billing.client.v1.refunds.create(
                    {'payment_intent': order['payment_intent'], 'metadata': {'report_order_id': order_id}},
                    options={'idempotency_key': 'report-quality-refund-'+order_id}))
        outcome = refund.get('status')
        if outcome not in ('succeeded', 'pending', 'requires_action'):
            outcome = 'payment_review'
        db.execute('UPDATE report_refunds SET status=?,refund_id=?,updated_at=? WHERE order_id=?',
                   (outcome, refund.get('id'), int(time.time()), order_id))
        if outcome == 'succeeded':
            db.execute("UPDATE purchases SET status='quality_refunded' WHERE order_id=?", (order_id,))


def retry_refunds(billing, *, user=None, rid=None, limit=10):
    """Bounded retry entrypoint for completion and owner recovery; no new orders."""
    if billing is None:
        return {'processed': 0, 'pending': True}
    with billing.accounts.db() as db:
        rows = db.execute("""SELECT order_id FROM report_refunds WHERE status IN ('pending','requires_action')
            AND (? IS NULL OR user_id=?) AND (? IS NULL OR review_id=?) ORDER BY updated_at LIMIT ?""",
                          (user, user, rid, rid, min(20, max(1, limit)))).fetchall()
    processed = 0
    for row in rows:
        try:
            refund_order(billing, row['order_id'])
            processed += 1
        except Exception:
            # Retain the outbox row unchanged. No provider secrets enter the UI.
            continue
    return {'processed': processed, 'attempted': len(rows)}
