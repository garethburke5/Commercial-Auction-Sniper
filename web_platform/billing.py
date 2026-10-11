"""Stripe-hosted checkout/portal and verified, idempotent entitlements.

Only configured price IDs map to plans. Browser redirects cannot grant access.
Subscription event payloads are notifications: read Stripe's current state while
holding the local transaction lock so concurrent/reordered deliveries cannot
apply an older captured subscription after a newer one.
"""
import time
import os
import uuid
import stripe
from fastapi import HTTPException
from .accounts import PLANS
from .database import begin_write

def plain(value):
    return value.to_dict() if hasattr(value,'to_dict') else value

class Billing:
    PRODUCTS = frozenset({'investment_report','legal_pack_report','featured_listing','data_export'})

    def __init__(self,accounts,secret,webhook_secret,prices,origin,one_off_prices=None,report_prices=None):
        self.accounts=accounts;self.secret=secret;self.webhook_secret=webhook_secret
        self.prices={k:v for k,v in prices.items() if k in PLANS and k!='free' and v}
        self.origin=origin.rstrip('/')
        self.client=stripe.StripeClient(secret) if secret else None
        self.report_prices={k:v for k,v in (report_prices or {}).items() if k in ('free','investor','professional') and v}
        self.one_off_prices={k:v for k,v in (one_off_prices or {}).items() if k in self.PRODUCTS and v}

    def configured(self):
        if not self.secret or not self.webhook_secret or not self.origin.startswith('https://'):
            raise HTTPException(503,'Billing is not enabled')
        if not self.secret.startswith(('sk_test_','rk_test_')) and os.getenv('BILLING_LIVE')!='true':
            raise HTTPException(503,'Live billing is disabled')

    def checkout(self,user,plan):
        self.configured()
        if plan not in self.prices: raise HTTPException(400,'Plan is not available')
        self._validate_price(self.prices[plan],plan,subscription=True)
        self.accounts.ensure(user)
        customer=self.accounts.customer(user)
        if not customer:
            customer=self.client.v1.customers.create({'metadata':{'account_id':user}},options={'idempotency_key':'account-'+user})['id']
            with self.accounts.db() as db: db.execute('UPDATE accounts SET customer_id=? WHERE user_id=?',(customer,user))
        # Existing subscribers manage their plan via Stripe, avoiding duplicate subscriptions.
        existing=plain(self.client.v1.subscriptions.list({'customer':customer,'status':'all','limit':100}))
        if any(s['status'] not in ('canceled','incomplete_expired') for s in existing['data']):
            return self.portal(user)
        session=self.client.v1.checkout.sessions.create({'customer':customer,'mode':'subscription',
            'line_items':[{'price':self.prices[plan],'quantity':1}],'client_reference_id':user,
            'integration_identifier':'auction_geek_membership_abkqmfzt',
            'success_url':self.origin+'/account/?checkout=returned','cancel_url':self.origin+'/account/'},
            options={'idempotency_key':f'checkout-{user}-{plan}-{int(time.time())//1800}'})
        return session['url']

    def portal(self,user):
        self.configured();customer=self.accounts.customer(user)
        if not customer: raise HTTPException(409,'No billing account exists')
        return self.client.v1.billing_portal.sessions.create({'customer':customer,'return_url':self.origin+'/account/'})['url']

    def purchase(self,user,product,property_id):
        """Server-priced one-off order. Payment never automatically publishes a listing."""
        if product in ('legal_pack_report','investment_report'):
            from acquisition_quality import paid_report_status
            quality = paid_report_status()
            if not quality['purchase_available']:
                raise HTTPException(503, quality['message'])
        self.configured()
        price_id=self.one_off_prices.get(product)
        report_plan=self.accounts.plan(user) if product=='legal_pack_report' else None
        if report_plan is not None:
            price_id=self.report_prices.get(report_plan)
        if not price_id:raise HTTPException(400,'Product is not available')
        if report_plan is not None:self._validate_price(price_id,report_plan)
        self.accounts.ensure(user)
        customer=self.accounts.customer(user)
        if not customer:
            customer=self.client.v1.customers.create({'metadata':{'account_id':user}},options={'idempotency_key':'account-'+user})['id']
            with self.accounts.db() as db:db.execute('UPDATE accounts SET customer_id=? WHERE user_id=?',(customer,user))
        with self.accounts.db() as db:
            begin_write(db)
            if product=='legal_pack_report':
                from .report_credits import credit_access
                rid=property_id.removeprefix('review:')
                if not property_id.startswith('review:') or not db.execute('SELECT 1 FROM reviews WHERE id=? AND user_id=?',(rid,user)).fetchone():
                    raise HTTPException(404,'Report not found')
                if credit_access(db,user,rid):raise HTTPException(409,'This report is already unlocked')
            existing=db.execute("SELECT * FROM purchases WHERE user_id=? AND product=? AND property_id=? AND status IN ('pending','paid_awaiting_fulfilment') ORDER BY created_at DESC LIMIT 1",(user,product,property_id)).fetchone()
            if existing:
                if existing['status']=='paid_awaiting_fulfilment':raise HTTPException(409,'This order is already paid')
                order=dict(existing)
            else:
                order={'order_id':uuid.uuid4().hex,'price_id':price_id}
                db.execute('INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES (?,?,?,?,?,?,?)',(order['order_id'],user,product,property_id,order['price_id'],'pending',int(time.time())))
        session=self.client.v1.checkout.sessions.create({'customer':customer,'mode':'payment',
            'line_items':[{'price':order['price_id'],'quantity':1}],'client_reference_id':user,
            'metadata':{'order_id':order['order_id']},'payment_intent_data':{'metadata':{'order_id':order['order_id']}},
            'integration_identifier':'auction_geek_report_cvnpwksx',
            'success_url':self.origin+'/account/?purchase=returned','cancel_url':self.origin+'/account/'},
            options={'idempotency_key':'order-'+order['order_id']})
        with self.accounts.db() as db:db.execute('UPDATE purchases SET session_id=? WHERE order_id=?',(session['id'],order['order_id']))
        return session['url']

    def _purchase_event(self,db,event):
        typ=event['type'];obj=event['data']['object']
        if typ.startswith('checkout.session.'):
            session=plain(self.client.v1.checkout.sessions.retrieve(obj['id'],{'expand':['line_items','payment_intent.latest_charge']}))
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
            if isinstance(intent,str):intent=plain(self.client.v1.payment_intents.retrieve(intent,{'expand':['latest_charge']}))
            charge=intent.get('latest_charge') or {}
            if isinstance(charge,str):charge=plain(self.client.v1.charges.retrieve(charge))
            if order['status'] in ('refund_review','payment_review'):status=order['status']
            elif charge.get('refunded') or charge.get('amount_refunded',0)>0:status='refund_review'
            elif charge.get('disputed'):status='payment_review'
            elif session.get('payment_status')=='paid' and session.get('status')=='complete':status='paid_awaiting_fulfilment'
            elif session.get('status')=='expired':status='expired'
            else:status='pending'
            db.execute('UPDATE purchases SET session_id=?,payment_intent=?,status=? WHERE order_id=?',(session['id'],intent.get('id'),status,order_id))
        elif typ in ('charge.refunded','charge.dispute.created','charge.dispute.closed'):
            charge=plain(self.client.v1.charges.retrieve(obj.get('charge') if typ.startswith('charge.dispute.') else obj['id']))
            db.execute("UPDATE report_credit_periods SET status='payment_review' WHERE invoice_id IN (SELECT invoice_id FROM report_credit_payments WHERE payment_intent=?)",(charge.get('payment_intent'),))
            # Manual review remains necessary after refunds/disputes; a late success cannot restore delivery.
            db.execute("UPDATE purchases SET status=? WHERE payment_intent=?",('refund_review' if charge.get('amount_refunded',0)>0 else 'payment_review',charge.get('payment_intent')))

    def _validate_price(self,price_id,plan,subscription=False):
        from .plans import CATALOGUE
        item=CATALOGUE.get(plan,{})
        amount=item.get('monthly_gbp' if subscription else 'additional_report_gbp')
        price=plain(self.client.v1.prices.retrieve(price_id))
        recurring=price.get('recurring') or {}
        if (amount is None or not price.get('active') or price.get('currency')!='gbp'
                or price.get('unit_amount')!=amount*100
                or bool(recurring)!=subscription
                or subscription and (recurring.get('interval')!='month' or recurring.get('interval_count')!=1)
                or price.get('livemode',False)!=(not self.secret.startswith(('sk_test_','rk_test_')))):
            raise HTTPException(503,'The configured price does not match the published offering')

    def _subscription(self,db,sid):
        sub=plain(self.client.v1.subscriptions.retrieve(sid))
        account=db.execute('SELECT user_id FROM accounts WHERE customer_id=?',(sub['customer'],)).fetchone()
        if not account:return sub,None
        items=sub.get('items',{}).get('data',[])
        inverse={v:k for k,v in self.prices.items()}
        plan=inverse.get(items[0]['price']['id'],'free') if len(items)==1 and items[0].get('quantity',1)==1 else 'free'
        until=int(sub.get('current_period_end') or (items[0].get('current_period_end') if items else 0) or 0)
        db.execute('''INSERT INTO subscriptions VALUES (?,?,?,?,?) ON CONFLICT(subscription_id)
            DO UPDATE SET user_id=excluded.user_id,plan=excluded.plan,status=excluded.status,valid_until=excluded.valid_until''',
            (sub['id'],account['user_id'],plan,sub['status'],until))
        return sub,account['user_id']

    def _invoice(self,db,iid):
        invoice=plain(self.client.v1.invoices.retrieve(iid,{'expand':['payments.data.payment.payment_intent']}))
        sid=invoice.get('subscription') or (invoice.get('parent') or {}).get('subscription_details',{}).get('subscription')
        if not sid:return
        sub,user=self._subscription(db,sid)
        if not user or invoice.get('customer')!=sub['customer']:return
        if invoice.get('status')!='paid':
            db.execute("UPDATE report_credit_periods SET status='payment_review' WHERE invoice_id=?",(iid,))
            return
        # Prorations/one-off invoice items cannot mint a fresh monthly allowance.
        if invoice.get('billing_reason') not in ('subscription_create','subscription_cycle'):return
        lines=invoice.get('lines') or {}
        if lines.get('has_more'):raise HTTPException(409,'Invoice requires billing review')
        inverse={v:k for k,v in self.prices.items()};eligible=[]
        for line in lines.get('data',[]):
            parent=(line.get('parent') or {}).get('subscription_item_details') or {}
            price=(line.get('price') or {}).get('id') or (line.get('pricing') or {}).get('price_details',{}).get('price')
            if price in inverse and not line.get('proration',parent.get('proration',False)) and line.get('quantity')==1:
                eligible.append((line,inverse[price]))
        if len(eligible)!=1 or invoice.get('currency')!='gbp':return
        line,plan=eligible[0];period=line.get('period') or {}
        start,end=int(period.get('start',0)),int(period.get('end',0))
        if end<=start or not 27*86400<=end-start<=32*86400:return
        from .report_credits import allowance
        count=allowance(plan)
        if not count:return
        payments=invoice.get('payments') or {}
        if payments.get('has_more'):raise HTTPException(409,'Invoice payments require billing review')
        intents=[]
        for payment in payments.get('data',[]):
            intent=(payment.get('payment') or {}).get('payment_intent')
            if intent:intents.append(intent.get('id') if isinstance(intent,dict) else intent)
        if invoice.get('payment_intent'):
            item=invoice['payment_intent'];intents.append(item.get('id') if isinstance(item,dict) else item)
        # Positive invoices need a traceable Stripe payment for refund handling.
        if invoice.get('amount_paid',0)>0 and not intents:raise HTTPException(409,'Invoice payment is not traceable')
        status='paid'
        for intent in set(intents):
            pi=plain(self.client.v1.payment_intents.retrieve(intent,{'expand':['latest_charge']}))
            charge=pi.get('latest_charge') or {}
            if isinstance(charge,str):charge=plain(self.client.v1.charges.retrieve(charge))
            if charge.get('refunded') or charge.get('amount_refunded',0)>0 or charge.get('disputed'):status='payment_review'
            db.execute('INSERT INTO report_credit_payments VALUES (?,?) ON CONFLICT DO NOTHING',(iid,intent))
        db.execute('''INSERT INTO report_credit_periods VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(subscription_id,period_start) DO NOTHING''',
            (sid,start,end,user,plan,count,iid,status))
        if status!='paid':db.execute("UPDATE report_credit_periods SET status='payment_review' WHERE invoice_id=?",(iid,))

    def webhook(self,body,signature):
        self.configured()
        try: event=plain(stripe.Webhook.construct_event(body,signature,self.webhook_secret))
        except (ValueError,stripe.SignatureVerificationError): raise HTTPException(400,'Invalid webhook signature')
        if event.get('livemode') and os.getenv('BILLING_LIVE')!='true':
            raise HTTPException(400,'Live billing is disabled')
        event_id=event['id'];typ=event['type']
        with self.accounts.db() as db:
            begin_write(db)
            if db.execute('SELECT 1 FROM webhook_events WHERE event_id=?',(event_id,)).fetchone(): return 'duplicate'
            if typ in ('checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.async_payment_failed','checkout.session.expired','charge.refunded','charge.dispute.created','charge.dispute.closed'):
                self._purchase_event(db,event)
            if typ in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'):
                self._subscription(db,event['data']['object']['id'])
            if typ in ('invoice.paid','invoice.payment_failed','invoice.voided','invoice.marked_uncollectible'):
                self._invoice(db,event['data']['object']['id'])
            db.execute('INSERT INTO webhook_events VALUES (?,?)',(event_id,int(time.time())))
        return 'processed'
