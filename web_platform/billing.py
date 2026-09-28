"""Stripe-hosted checkout/portal and verified, idempotent entitlements.

Only configured price IDs map to plans. Browser redirects cannot grant access.
Subscription event payloads are notifications: read Stripe's current state while
holding the local transaction lock so concurrent/reordered deliveries cannot
apply an older captured subscription after a newer one.
"""
import time
import stripe
from fastapi import HTTPException
from .accounts import PLANS

class Billing:
    def __init__(self,accounts,secret,webhook_secret,prices,origin):
        self.accounts=accounts;self.secret=secret;self.webhook_secret=webhook_secret
        self.prices={k:v for k,v in prices.items() if k in PLANS and k!='free' and v}
        self.origin=origin.rstrip('/')

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

    def webhook(self,body,signature):
        self.configured()
        try: event=stripe.Webhook.construct_event(body,signature,self.webhook_secret)
        except (ValueError,stripe.SignatureVerificationError): raise HTTPException(400,'Invalid webhook signature')
        event_id=event['id'];typ=event['type']
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM webhook_events WHERE event_id=?',(event_id,)).fetchone(): return 'duplicate'
            if typ in ('customer.subscription.created','customer.subscription.updated','customer.subscription.deleted'):
                sub=stripe.Subscription.retrieve(event['data']['object']['id'],api_key=self.secret)
                account=db.execute('SELECT user_id FROM accounts WHERE customer_id=?',(sub['customer'],)).fetchone()
                if account:
                    items=sub.get('items',{}).get('data',[])
                    inverse={v:k for k,v in self.prices.items()}
                    # Ambiguous multi-plan subscriptions fail closed.
                    plan=inverse.get(items[0]['price']['id'],'free') if len(items)==1 else 'free'
                    until=int(sub.get('current_period_end') or (items[0].get('current_period_end') if items else 0) or 0)
                    db.execute('INSERT OR REPLACE INTO subscriptions VALUES (?,?,?,?,?)',
                               (sub['id'],account['user_id'],plan,sub['status'],until))
            db.execute('INSERT INTO webhook_events VALUES (?,?)',(event_id,int(time.time())))
        return 'processed'
