"""Public availability flags, without publishing secrets or accepting payments.

Configured credentials are not proof of a completed customer transaction. Stripe
prices and signed payment events are still validated by the checkout handlers.
"""
import os


def availability(environ=None):
    env = os.environ if environ is None else environ
    live_key = env.get('STRIPE_SECRET_KEY', '').startswith(('sk_live_', 'rk_live_'))
    configured = bool(live_key and env.get('STRIPE_WEBHOOK_SECRET')
                      and env.get('PUBLIC_ORIGIN', '').startswith('https://'))
    live = configured and env.get('BILLING_LIVE') == 'true'
    tax_ready = env.get('BILLING_TAX_MODE') == 'not_registered' or (
        env.get('BILLING_TAX_MODE') == 'inclusive_manual' and bool(env.get('STRIPE_TAX_RATE')))
    memberships = live and tax_ready and all(env.get(key) for key in
        ('STRIPE_PRICE_INVESTOR', 'STRIPE_PRICE_PROFESSIONAL'))
    reports = live and tax_ready and env.get('PAID_REPORTS_ENABLED') == 'true' and all(env.get(key) for key in
        ('STRIPE_PRICE_LEGAL_PACK_REPORT', 'STRIPE_PRICE_REPORT_INVESTOR', 'STRIPE_PRICE_REPORT_PROFESSIONAL'))
    history = live and all(env.get(key) == 'true' for key in
        ('HISTORY_SALES_ENABLED', 'HISTORY_ARCHIVE_PRIVATE', 'HISTORY_QUALITY_APPROVED'))
    history = history and env.get('HISTORY_TAX_MODE') in ('not_registered', 'inclusive_manual') and all(
        env.get(key) for key in ('STRIPE_PRICE_PROPERTY_HISTORY', 'STRIPE_PRICE_HISTORY_DAY_PASS'))
    if env.get('HISTORY_TAX_MODE') == 'inclusive_manual':
        history = history and bool(env.get('HISTORY_STRIPE_TAX_RATE'))
    return {'live_billing_configured': configured,
            'membership_checkout_available': bool(memberships),
            'report_checkout_available': bool(reports),
            'history_checkout_available': bool(history)}
