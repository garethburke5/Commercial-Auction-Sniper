"""Read-only live payment preflight, with an explicit idempotent UK VAT setup.

Uses STRIPE_SECRET_KEY from the process environment; never accepts it as an
argument or prints provider errors. Does not enable billing, Stripe Tax, change
registrations, create payments, or decide overseas tax liability.
"""
import argparse
from decimal import Decimal, InvalidOperation
import json
import os

ACCOUNT = 'acct_1UO227RpkJti4bUn'
COMPANY = 'Burke Commercial Ltd'
BUSINESS_VAT_ID = 'GB528469357'
PRICES = {
    'investor': ('price_1UY2r4RpkJti4bUnTrZsTywn', 1500, True, 'inclusive', 'auctiongeek_investor'),
    'investor_pro': ('price_1UY2rYRpkJti4bUnH2qVC8vI', 2500, True, 'inclusive', 'auctiongeek_investor_pro'),
    'report_uk': ('price_1UY2roRpkJti4bUnrMWa7a8h', 1900, False, 'inclusive', 'auctiongeek_full_investment_report'),
    'report_investor': ('price_1UY2s7RpkJti4bUn5rg4Imdw', 1500, False, 'inclusive', 'auctiongeek_full_investment_report'),
    'report_pro': ('price_1UY2sQRpkJti4bUn5LPKtpeV', 1200, False, 'inclusive', 'auctiongeek_full_investment_report'),
    'history': ('price_1UY2sgRpkJti4bUnhBqFzYbZ', 299, False, 'inclusive', 'auctiongeek_property_history'),
    'day_pass': ('price_1UY2suRpkJti4bUnEtDBVaV2', 500, False, 'inclusive', 'auctiongeek_history_day_pass'),
    'report_overseas': ('price_1UYELbRpkJti4bUnlrnQIlHr', 1900, False, 'exclusive', 'auctiongeek_full_investment_report'),
}
WEBHOOK = 'we_1UY2utRpkJti4bUnOrJZSdJr'
WEBHOOK_URL = 'https://auction-sniper-private-api.onrender.com/api/billing/webhook'
EVENTS = frozenset({
    'checkout.session.completed', 'checkout.session.async_payment_succeeded',
    'checkout.session.async_payment_failed', 'checkout.session.expired',
    'charge.refunded', 'charge.dispute.created', 'charge.dispute.closed',
    'customer.subscription.created', 'customer.subscription.updated',
    'customer.subscription.deleted', 'invoice.paid', 'invoice.payment_failed',
    'invoice.voided', 'invoice.marked_uncollectible',
})
PORTAL = 'bpc_1UYELyRpkJti4bUnEXhY9OnW'


class SetupError(Exception):
    """Messages are fixed operator guidance, never raw Stripe responses."""


def plain(value):
    return value.to_dict() if hasattr(value, 'to_dict') else value


def normal_name(value):
    return ' '.join(str(value or '').casefold().split())


def matches_rate(rate, inclusive):
    try:
        percentage = Decimal(str(rate.get('percentage')))
    except InvalidOperation:
        return False
    return (rate.get('active') is True and rate.get('livemode') is True
            and rate.get('inclusive') is inclusive and percentage == Decimal('20')
            and rate.get('country') == 'GB' and not rate.get('state')
            and rate.get('display_name', '').casefold() == 'vat'
            and rate.get('tax_type') in (None, 'vat'))


def inspect_account(client):
    account = plain(client.v1.accounts.retrieve_current())
    if account.get('id') != ACCOUNT:
        raise SetupError('The key belongs to a different Stripe account; no changes made.')
    if normal_name((account.get('company') or {}).get('name')) != normal_name(COMPANY):
        raise SetupError('Stripe legal company name must be confirmed as Burke Commercial Ltd; no changes made.')
    return {'account_id': ACCOUNT,
            'charges_enabled': account.get('charges_enabled') is True,
            'payouts_enabled': account.get('payouts_enabled') is True}


def inspect_prices(client):
    checked = {}
    for label, (pid, amount, subscription, behavior, product) in PRICES.items():
        price = plain(client.v1.prices.retrieve(pid))
        recurring = price.get('recurring') or {}
        product_id = price.get('product')
        if isinstance(product_id, dict):
            product_id = product_id.get('id')
        valid = (price.get('active') is True and price.get('livemode') is True
                 and price.get('currency') == 'gbp' and price.get('unit_amount') == amount
                 and price.get('tax_behavior') == behavior and product_id == product
                 and bool(recurring) == subscription)
        if subscription:
            valid = valid and recurring.get('interval') == 'month' and recurring.get('interval_count') == 1
        if not valid:
            raise SetupError(f'Configured Stripe price failed validation: {label}; no changes made.')
        checked[label] = {'id': pid, 'amount_pence': amount, 'tax_behavior': behavior}
    return checked


def inspect_delivery(client):
    webhook = plain(client.v1.webhook_endpoints.retrieve(WEBHOOK))
    if (webhook.get('livemode') is not True or webhook.get('status') != 'enabled'
            or webhook.get('url') != WEBHOOK_URL
            or not EVENTS.issubset(set(webhook.get('enabled_events') or []))):
        raise SetupError('Live webhook configuration needs correction; no changes made.')
    portal = plain(client.v1.billing_portal.configurations.retrieve(PORTAL))
    features = portal.get('features') or {}
    cancel = features.get('subscription_cancel') or {}
    if (portal.get('active') is not True or portal.get('livemode') is not True
            or portal.get('is_default') is not True
            or portal.get('default_return_url') != 'https://auctiongeek.co.uk/account/'
            or cancel.get('enabled') is not True or cancel.get('mode') != 'at_period_end'
            or (features.get('subscription_update') or {}).get('enabled') is True
            or not all((features.get(name) or {}).get('enabled') is True
                       for name in ('invoice_history', 'payment_method_update'))):
        raise SetupError('Live customer portal configuration needs correction; no changes made.')


def business_vat_id(client, *, apply=False):
    """Register the owner's supplied number and preserve other invoice defaults.

    This stores an existing registration in Stripe; it does not register the
    business with HMRC, enable Stripe Tax, or assert HMRC validation.
    """
    inspect_account(client)
    account = plain(client.v1.accounts.retrieve_current())
    entries = [plain(item) for item in client.v1.tax_ids.list(
        {'owner': {'type': 'self'}, 'limit': 100}).auto_paging_iter()]
    uk = [item for item in entries if item.get('type') == 'gb_vat']
    if any(str(item.get('value', '')).replace(' ', '').upper() != BUSINESS_VAT_ID for item in uk):
        raise SetupError('Stripe already holds a different business UK VAT number; review the legal entity before changing it.')
    matching = sorted(uk, key=lambda item: item['id'])
    tax_id = matching[0] if matching else None
    if tax_id is None and apply:
        created = plain(client.v1.tax_ids.create(
            {'owner': {'type': 'self'}, 'type': 'gb_vat', 'value': BUSINESS_VAT_ID},
            options={'idempotency_key': 'auctiongeek-business-gb-vat-528469357-v1'}))
        tax_id = plain(client.v1.tax_ids.retrieve(created['id']))
    if tax_id is not None:
        owner = tax_id.get('owner') or {}
        owner_ok = owner.get('type') == 'self' or (
            owner.get('type') == 'account' and owner.get('account') == ACCOUNT)
        if (not owner_ok or tax_id.get('livemode') is not True
                or tax_id.get('type') != 'gb_vat'
                or str(tax_id.get('value', '')).replace(' ', '').upper() != BUSINESS_VAT_ID):
            raise SetupError('Business VAT ID failed read-back validation; invoice defaults were not changed.')
    defaults = ((account.get('settings') or {}).get('invoices') or {}).get('default_account_tax_ids') or []
    defaults = [item['id'] if isinstance(item, dict) else item for item in defaults]
    if apply and tax_id['id'] not in defaults:
        client.v1.accounts.update(ACCOUNT, {'settings': {'invoices': {
            'default_account_tax_ids': defaults + [tax_id['id']]}}})
        account = plain(client.v1.accounts.retrieve_current())
        defaults = ((account.get('settings') or {}).get('invoices') or {}).get('default_account_tax_ids') or []
        defaults = [item['id'] if isinstance(item, dict) else item for item in defaults]
        if tax_id['id'] not in defaults:
            raise SetupError('Business VAT ID exists but its invoice default was not confirmed.')
    return {'tax_id': tax_id['id'] if tax_id else None,
            'included_on_invoices': bool(tax_id and tax_id['id'] in defaults),
            'hmrc_verification_claimed': False}


def run(client, *, apply=False):
    result = inspect_account(client)
    result['prices'] = inspect_prices(client)
    inspect_delivery(client)
    # Complete read-only validation before the first possible write. Pagination
    # prevents duplicates when matching rates are beyond the first 100 results.
    rates = [plain(rate) for rate in client.v1.tax_rates.list({'active': True, 'limit': 100}).auto_paging_iter()]
    selected = {}
    for inclusive, label in ((True, 'uk_inclusive'), (False, 'uk_exclusive')):
        matches = sorted((r for r in rates if matches_rate(r, inclusive)), key=lambda r: r['id'])
        selected[label] = matches[0]['id'] if matches else None
    result['rates'] = selected
    result['created'] = []
    if apply:
        for inclusive, label in ((True, 'uk_inclusive'), (False, 'uk_exclusive')):
            if selected[label]:
                continue
            created = plain(client.v1.tax_rates.create({
                'display_name': 'VAT', 'percentage': 20, 'inclusive': inclusive,
                'country': 'GB', 'jurisdiction': 'United Kingdom',
                'description': 'Auction Geek UK standard VAT. Apply only where UK VAT is due.',
            }, options={'idempotency_key': f'auctiongeek-uk-vat-20-{label}-v1'}))
            verified = plain(client.v1.tax_rates.retrieve(created['id']))
            if not matches_rate(verified, inclusive):
                raise SetupError('Created rate did not pass read-back validation; stop and review Stripe tax rates.')
            selected[label] = verified['id']
            result['created'].append(label)
    result['checkout_enabled_by_this_command'] = False
    result['remaining'] = [
        'Confirm business VAT ID on Stripe invoices (owner supplied GB528469357).',
        'Complete customer-location and overseas tax treatment before routing report checkout.',
        'Verify the live deployment and configured VAT rates before enabling checkout.',
        'Verify signed payment fulfilment and customer access end to end.',
    ]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply-uk-vat', action='store_true',
                        help='Create missing UK 20%% inclusive/exclusive manual rates after validation.')
    parser.add_argument('--apply-business-vat-id', action='store_true',
                        help='Store the owner-supplied business VAT number and include it on invoices.')
    args = parser.parse_args(argv)
    secret = os.environ.get('STRIPE_SECRET_KEY', '')
    if not secret.startswith(('rk_live_', 'sk_live_')):
        print(json.dumps({'error': 'Set the existing live STRIPE_SECRET_KEY in the secure process environment.'}))
        return 2
    try:
        import stripe
        client = stripe.StripeClient(secret)
        result = run(client, apply=args.apply_uk_vat)
        if args.apply_business_vat_id:
            result['business_vat'] = business_vat_id(client, apply=True)
    except SetupError as exc:
        print(json.dumps({'error': str(exc)}))
        return 2
    except Exception:
        # Stripe/network exception bodies can contain request details. Do not log
        # them, tracebacks, environment contents, or the key, even on failure.
        print(json.dumps({'error': 'Stripe setup could not complete. Check key permissions and connectivity; rerun the read-only check before retrying changes.'}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
