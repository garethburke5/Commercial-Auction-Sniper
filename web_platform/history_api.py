"""Premium content is rendered only after server-side access checks."""
from functools import lru_cache
from fastapi import Header, HTTPException
from pydantic import BaseModel
from .history_access import require_access, sales_ready, offers

def install(app,site,user,current_catalogue):
    @lru_cache(maxsize=1)
    def market_for(catalogue):
        from .market_context import MarketContext
        return MarketContext(catalogue)

    def property_row(pid):
        row=current_catalogue().rows.get(pid)
        if not row:raise HTTPException(404,'Unknown property')
        return row

    @app.get('/api/history/products')
    def products():
        from .payment_availability import availability
        available=availability()['history_checkout_available']
        return {'purchases_available':available,'products':offers()}

    @app.get('/api/history/{property_id}')
    def history(property_id:str,authorization:str|None=Header(default=None)):
        uid,accounts,_=user(authorization)
        row=property_row(property_id)
        entitlement=require_access(accounts,uid,row)
        # Use the current catalogue; do not serve a stale site's cached archive.
        market=market_for(current_catalogue()).for_property(row)
        html=site.env.get_template('history_private.html').render(
            row=row,history=market['history'],market=market,kind='private-history')
        return {'access':entitlement,'html':html}

    class HistoryPurchase(BaseModel):
        product:str
        property_id:str

    def buy(body,authorization,sandbox):
        uid,_,billing=user(authorization)
        row=property_row(body.property_id)
        if not sandbox and not sales_ready():raise HTTPException(503,'History purchases are not open yet')
        context=market_for(current_catalogue()).for_property(row)
        if not context['history'] and not context.get('related_interests') and not context['observations']:
            raise HTTPException(409,'There is no linked history to unlock for this property yet')
        from .history_billing import purchase
        return {'url':purchase(billing,uid,body.product,row,sandbox=sandbox)}

    @app.post('/api/history/checkout')
    def checkout(body:HistoryPurchase,authorization:str|None=Header(default=None)):
        return buy(body,authorization,False)

    @app.post('/api/admin/history/checkout')
    def sandbox_checkout(body:HistoryPurchase,authorization:str|None=Header(default=None)):
        from .accounts import require_owner
        uid,_,_=user(authorization);require_owner(uid)
        return buy(body,authorization,True)
