"""Stripe-hosted checkout/portal and verified, idempotent entitlements.

Only configured price IDs map to plans. Browser redirects cannot grant access.
Subscription event payloads are notifications: read Stripe's current state while
holding the local transaction lock so concurrent/reordered deliveries cannot
apply an older captured subscription after a newer one.
"""
import time
import uuid
import stripe
from fastapi import HTTPException
from .accounts import PLANS
from .database import begin_write

class Billing:
    PRODUCTS = frozenset({'investment_report','legal_pack_report','featured_listing','data_export'})

    def __init__(self,accounts,secret,webhook_secret,prices,origin,one_off_prices=None):
        self.accounts=accounts;self.secret=secret;self.webhook_secret=webhook_secret
        self.prices={k:v for k,v in prices.items() if k in PLANS and k!='free' and v}
        self.origin=origin.rstrip('/')
        self.one_off_prices={k:v for k,v in (one_off_prices or {}).items() if k in self.PRODUCTS and v}

    def configured(self):
        if not self.secret or not self.webhook_secret or not self.origin.startswith('https://'):
            raise HTTPException(503,'Billing is not enabled')

    def checkout(self,user,plan):
        self.configured()
        if plan not in self.prices: raise HTTPException(400,'Plan is not available')
        self.accounts.ensure(user)
        customer=self.accounts.customer(user)
        if not customer:
            customer=stripe.Customer.create(api_key=self.secret,metadata={'account_id':user},idempotency_key='account-'+user)['id']
            with self.accounts.db() as db: db.execute('UPDATE accounts SET customer_id=? WHERE user_id=?',(customer,user))
        # Existing subscribers manage their plan via Stripe, avoiding duplicate subscriptions.
        existing=stripe.Subscription.list(customer=customer,status='all',limit=100,api_key=self.secret)
        if any(s['status'] not in ('canceled','incomplete_expired') for s in existing['data']):
            return self.portal(user)
        session=stripe.checkout.Session.create(api_key=self.secret,customer=customer,mode='subscription',
            line_items=[{'price':self.prices[plan],'quantity':1}],client_reference_id=user,
            success_url=self.origin+'/account/?checkout=returned',cancel_url=self.origin+'/account/',
            idempotency_key=f'checkout-{user}-{plan}-{int(time.time())//1800}')
        return session['url']

    def portal(self,user):
        self.configured();customer=self.accounts.customer(user)
        if not customer: raise HTTPException(409,'No billing account exists')
        return stripe.billing_portal.Session.create(api_key=self.secret,customer=customer,return_url=self.origin+'/account/')['url']

    def purchase(self,user,product,property_id):
        """Server-priced one-off order. Payment never automatically publishes a listing."""
        if product == 'legal_pack_report':
            from acquisition_quality import paid_report_status
            quality = paid_report_status()
            if not quality['purchase_available']:
                raise HTTPException(503, quality['message'])
        self.configured()
        if product not in self.one_off_prices:raise HTTPException(400,'Product is not available')
        self.accounts.ensure(user)
        customer=self.accounts.customer(user)
        if not customer:
            customer=stripe.Customer.create(api_key=self.secret,metadata={'account_id':user},idempotency_key='account-'+user)['id']
            with self.accounts.db() as db:db.execute('UPDATE accounts SET customer_id=? WHERE user_id=?',(customer,user))
        with self.accounts.db() as db:
            begin_write(db)
            existing=db.execute("SELECT * FROM purchases WHERE user_id=? AND product=? AND property_id=? AND status IN ('pending','paid_awaiting_fulfilment') ORDER BY created_at DESC LIMIT 1",(user,product,property_id)).fetchone()
            if existing:
                if existing['status']=='paid_awaiting_fulfilment':raise HTTPException(409,'This order is already paid')
                order=dict(existing)
            else:
                order={'order_id':uuid.uuid4().hex,'price_id':self.one_off_prices[product]}
                db.execute('INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES (?,?,?,?,?,?,?)',(order['order_id'],user,product,property_id,order['price_id'],'pending',int(time.time())))
        session=stripe.checkout.Session.create(api_key=self.secret,customer=customer,mode='payment',
            line_items=[{'price':order['price_id'],'quantity':1}],client_reference_id=user,
            metadata={'order_id':order['order_id']},payment_intent_data={'metadata':{'order_id':order['order_id']}},
            success_url=self.origin+'/account/?purchase=returned',cancel_url=self.origin+'/account/',
            idempotency_key='order-'+order['order_id'])
        with self.accounts.db() as db:db.execute('UPDATE purchases SET session_id=? WHERE order_id=?',(session['id'],order['order_id']))
        return session['url']

    def _purchase_event(self,db,event):
        typ=event['type'];obj=event['data']['object']
        if typ.startswith('checkout.session.'):
            session=stripe.checkout.Session.retrieve(obj['id'],expand=['line_items','payment_intent.latest_charge'],api_key=self.secret)
            if session.get('mode')!='payment':return
            order_id=(session.get('metadata') or {}).get('order_id')
            order=db.execute('SELECT * FROM purchases WHERE order_id=?',(order_id,)).fetchone()
            if not order:return
            account=db.execute('SELECT customer_id FROM accounts WHERE user_id=?',(order['user_id'],)).fetchone()
            items=(session.get('line_items') or {}).get('data',[])
            if (session.get('customer')!=account['customer_id'] or session.get('client_reference_id')!=order['user_id']
                or (order['session_id'] and session['id']!=order['session_id'])
                or len(items)!=1 or items[0].get('quantity')!=1 or items[0].get('price',{}).get('id')!=order['price_id']):
                raise HTTPException(400,'Payment does not match this order')
            intent=session.get('payment_intent') or {}
            if isinstance(intent,str):intent=stripe.PaymentIntent.retrieve(intent,expand=['latest_charge'],api_key=self.secret)
            charge=intent.get('latest_charge') or {}
            if isinstance(charge,str):charge=stripe.Charge.retrieve(charge,api_key=self.secret)
            if order['status'] in ('refund_review','payment_review'):status=order['status']
            elif charge.get('refunded') or charge.get('amount_refunded',0)>0:status='refund_review'
            elif charge.get('disputed'):status='payment_review'
            elif session.get('payment_status')=='paid' and session.get('status')=='complete':status='paid_awaiting_fulfilment'
            elif session.get('status')=='expired':status='expired'
            else:status='pending'
            db.execute('UPDATE purchases SET session_id=?,payment_intent=?,status=? WHERE order_id=?',(session['id'],intent.get('id'),status,order_id))
        elif typ in ('charge.refunded','charge.dispute.created','charge.dispute.closed'):
            charge=stripe.Charge.retrieve(obj.get('charge') if typ.startswith('charge.dispute.') else obj['id'],api_key=self.secret)
            # Manual review remains necessary after refunds/disputes; a late success cannot restore delivery.
            db.execute("UPDATE purchases SET status=? WHERE payment_intent=?",('refund_review' if charge.get('amount_refunded',0)>0 else 'payment_review',charge.get('payment_intent')))

    def webhook(self,body,signature):
        self.configured()
        try: event=stripe.Webhook.construct_event(body,signature,self.webhook_secret)
        except (ValueError,stripe.SignatureVerificationError): raise HTTPException(400,'Invalid webhook signature')
        event_id=event['id'];typ=event['type']
        with self.accounts.db() as db:
            begin_write(db)
            if db.execute('SELECT 1 FROM webhook_events WHERE event_id=?',(event_id,)).fetchone(): return 'duplicate'
            if typ in ('checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.async_payment_failed','checkout.session.expired','charge.refunded','charge.dispute.created','charge.dispute.closed'):
                self._purchase_event(db,event)
            if typ in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'):
                sub=stripe.Subscription.retrieve(event['data']['object']['id'],api_key=self.secret)
                account=db.execute('SELECT user_id FROM accounts WHERE customer_id=?',(sub['customer'],)).fetchone()
                if account:
                    items=sub.get('items',{}).get('data',[])
                    inverse={v:k for k,v in self.prices.items()}
                    # Ambiguous multi-plan subscriptions fail closed.
                    plan=inverse.get(items[0]['price']['id'],'free') if len(items)==1 else 'free'
                    until=int(sub.get('current_period_end') or (items[0].get('current_period_end') if items else 0) or 0)
                    db.execute('''INSERT INTO subscriptions VALUES (?,?,?,?,?) ON CONFLICT(subscription_id)
                        DO UPDATE SET user_id=excluded.user_id,plan=excluded.plan,status=excluded.status,valid_until=excluded.valid_until''',
                               (sub['id'],account['user_id'],plan,sub['status'],until))
            db.execute('INSERT INTO webhook_events VALUES (?,?)',(event_id,int(time.time())))
        return 'processed'
