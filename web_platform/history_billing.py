"""History Checkout uses stored server terms and the existing signed webhook."""
import os
import time
import uuid
from fastapi import HTTPException
from .database import begin_write
from .history_access import PRODUCTS, access, offers, sales_ready, subject_key

def purchase(billing,user,product,row,*,sandbox=False):
    from .billing import plain
    if product not in PRODUCTS:raise HTTPException(400,'Unknown history product')
    if sandbox:
        from .accounts import require_owner
        require_owner(user)
        if not billing.secret or not billing.secret.startswith(('sk_test_','rk_test_')) or os.getenv('BILLING_LIVE')=='true':
            raise HTTPException(409,'History testing requires sandbox keys and live billing disabled')
    elif not sales_ready():raise HTTPException(503,'History purchases are not open yet')
    billing.configured()
    offer=offers()[product]
    if not offer['enabled']:raise HTTPException(503,'This pass is not available yet')
    key=subject_key(row)
    if not key:raise HTTPException(409,'The property address and tenure need checking before purchase')
    price_id=billing.one_off_prices.get(product)
    if not price_id:raise HTTPException(503,'History checkout is not configured')
    price=plain(billing.client.v1.prices.retrieve(price_id))
    test=billing.secret.startswith(('sk_test_','rk_test_'))
    if (not price.get('active') or price.get('currency')!='gbp' or price.get('unit_amount')!=offer['amount_pence']
        or price.get('recurring') or price.get('livemode',False)==test):
        raise HTTPException(503,'Configured history price does not match the published price')
    # Tax setup is explicit. Never infer VAT registration or add a paid Tax service.
    tax_mode=os.getenv('HISTORY_TAX_MODE','')
    if not sandbox and tax_mode not in ('not_registered','inclusive_manual'):
        raise HTTPException(503,'History tax treatment has not been confirmed')
    tax_rates=[]
    if tax_mode=='inclusive_manual':
        tax_id=os.getenv('HISTORY_STRIPE_TAX_RATE','')
        if not tax_id:raise HTTPException(503,'History tax rate is not configured')
        tax=plain(billing.client.v1.tax_rates.retrieve(tax_id))
        if not tax.get('active') or not tax.get('inclusive') or tax.get('livemode',False)==test:
            raise HTTPException(503,'History requires an active inclusive tax rate in this environment')
        tax_rates=[tax_id]
    billing.accounts.ensure(user)
    customer=billing.accounts.customer(user)
    if not customer:
        customer=billing.client.v1.customers.create({'metadata':{'account_id':user}},options={'idempotency_key':'account-'+user})['id']
        with billing.accounts.db() as db:db.execute('UPDATE accounts SET customer_id=? WHERE user_id=?',(customer,user))
    with billing.accounts.db() as db:
        begin_write(db)
        if access(billing.accounts,user,row,db=db)['allowed']:
            raise HTTPException(409,'You already have access to this property history')
        # One pending history checkout per account: no overlapping pass/property
        # orders, even in parallel tabs. A known expired session can be replaced.
        pending=db.execute('''SELECT p.* FROM purchases p JOIN history_order_terms t ON t.order_id=p.order_id
            WHERE p.user_id=? AND p.status='pending' ORDER BY p.created_at DESC LIMIT 1''',(user,)).fetchone()
        if pending:
            if not pending['session_id'] and int(time.time())-pending['created_at']>=23*3600:
                raise HTTPException(409,'An earlier checkout needs checking before another payment. Contact team@auctiongeek.co.uk.')
            if pending['session_id']:
                old=plain(billing.client.v1.checkout.sessions.retrieve(pending['session_id']))
                if old.get('status')=='expired':
                    db.execute("UPDATE purchases SET status='expired' WHERE order_id=?",(pending['order_id'],));pending=None
                elif old.get('status')=='complete':raise HTTPException(409,'Your payment is being confirmed. Please do not pay again.')
            if pending and (pending['product']!=product or pending['property_id']!=row['id']):
                raise HTTPException(409,'You already have a history checkout in progress. Finish it or wait for it to expire before starting another.')
        if pending:
            order_id=pending['order_id'];price_id=pending['price_id']
        else:
            order_id=uuid.uuid4().hex
            db.execute('INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES (?,?,?,?,?,?,?)',
                       (order_id,user,product,row['id'],price_id,'pending',int(time.time())))
            db.execute('INSERT INTO history_order_terms(order_id,subject_key,amount_pence,duration_seconds,terms_version) VALUES (?,?,?,?,?)',
                       (order_id,key,offer['amount_pence'],offer['duration_seconds'],'history-2026-10-20'))
    # Commit the order before contacting Stripe. A lost response must reuse it.
    line={'price':price_id,'quantity':1}
    if tax_rates:line['tax_rates']=tax_rates
    session=billing.client.v1.checkout.sessions.create({
        'customer':customer,'mode':'payment','line_items':[line], 'client_reference_id':user,
        'metadata':{'order_id':order_id}, 'payment_intent_data':{'metadata':{'order_id':order_id}},
        'integration_identifier':'auction_geek_history_qmztbskv',
        'success_url':billing.origin+row['path']+'?history_purchase=returned#history',
        'cancel_url':billing.origin+row['path']+'#history'},
        options={'idempotency_key':'history-order-'+order_id})
    with billing.accounts.db() as db:
        db.execute('UPDATE purchases SET session_id=? WHERE order_id=?',(session['id'],order_id))
    return session['url']

def validate_payment(db,order,session,intent,charge,test):
    """Re-retrieved Stripe values must match immutable terms before any grant."""
    terms=db.execute('SELECT * FROM history_order_terms WHERE order_id=?',(order['order_id'],)).fetchone()
    if not terms:raise HTTPException(409,'History purchase terms are missing')
    if session.get('payment_status')!='paid' or session.get('status')!='complete':return
    if (session.get('livemode',False)==test or session.get('currency')!='gbp'
        or session.get('amount_total')!=terms['amount_pence']
        or intent.get('status')!='succeeded' or intent.get('currency')!='gbp'
        or intent.get('amount_received')!=terms['amount_pence']
        or intent.get('customer')!=session.get('customer')
        or charge.get('payment_intent')!=intent.get('id')
        or not charge.get('paid')):
        raise HTTPException(400,'History payment amount, currency or payment identity does not match')

def grant(db,order,session,charge,status):
    if status!='paid_awaiting_fulfilment':return
    terms=db.execute('SELECT * FROM history_order_terms WHERE order_id=?',(order['order_id'],)).fetchone()
    if terms['paid_at'] is not None:return  # Replay must never extend a pass.
    paid_at=int(time.time())
    expires=paid_at+terms['duration_seconds'] if terms['duration_seconds'] else None
    db.execute('''UPDATE history_order_terms SET paid_at=?,expires_at=?,currency=?,total_pence=?,tax_pence=?,receipt_url=?
        WHERE order_id=? AND paid_at IS NULL''',(paid_at,expires,session['currency'],session['amount_total'],
        (session.get('total_details') or {}).get('amount_tax',0),charge.get('receipt_url'),order['order_id']))
