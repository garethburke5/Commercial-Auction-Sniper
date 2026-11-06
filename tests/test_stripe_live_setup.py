import copy
import json
from types import SimpleNamespace as NS

import pytest

from scripts import stripe_live_setup as setup


def rate(ident='txr_existing', inclusive=True, **changes):
    return dict(id=ident, active=True, livemode=True, inclusive=inclusive,
                percentage=20, country='GB', state=None, display_name='VAT', **changes)


class Rates:
    def __init__(self, rates=()):
        self.data = list(rates)
        self.writes = []

    def list(self, params):
        assert params == {'active': True, 'limit': 100}
        return NS(auto_paging_iter=lambda: iter(self.data))

    def create(self, params, *, options):
        self.writes.append((params, options))
        item = dict(params, id='txr_' + str(len(self.writes)), active=True, livemode=True)
        self.data.append(item)
        return item

    def retrieve(self, ident):
        return next(r for r in self.data if r['id'] == ident)


def client(rates=()):
    prices = {}
    for _, (pid, amount, recurring, behavior, product) in setup.PRICES.items():
        prices[pid] = dict(id=pid, active=True, livemode=True, currency='gbp',
                           unit_amount=amount, tax_behavior=behavior, product=product,
                           recurring={'interval': 'month', 'interval_count': 1} if recurring else None)
    account = {'id': setup.ACCOUNT, 'company': {'name': setup.COMPANY},
               'charges_enabled': True, 'payouts_enabled': True}
    webhook = {'livemode': True, 'status': 'enabled', 'url': setup.WEBHOOK_URL,
               'enabled_events': list(setup.EVENTS)}
    portal = {'active': True, 'livemode': True, 'is_default': True,
              'default_return_url': 'https://auctiongeek.co.uk/account/',
              'features': {'subscription_cancel': {'enabled': True, 'mode': 'at_period_end'},
                           'subscription_update': {'enabled': False},
                           'invoice_history': {'enabled': True},
                           'payment_method_update': {'enabled': True}}}
    c = NS(v1=NS(accounts=NS(retrieve_current=lambda: account), prices=NS(retrieve=prices.__getitem__),
                 webhook_endpoints=NS(retrieve=lambda _: webhook),
                 billing_portal=NS(configurations=NS(retrieve=lambda _: portal)), tax_rates=Rates(rates)))
    return c, account, prices, webhook, portal


def test_default_is_read_only_and_reports_missing_rates():
    c, *_ = client()
    result = setup.run(c)
    assert not c.v1.tax_rates.writes
    assert result['rates'] == {'uk_inclusive': None, 'uk_exclusive': None}
    assert not result['checkout_enabled_by_this_command']
    assert result['prices']['report_uk']['amount_pence'] == 1900
    assert result['prices']['report_overseas']['tax_behavior'] == 'exclusive'


def test_apply_is_idempotent_and_keeps_price_catalogue_unchanged():
    c, _, prices, *_ = client()
    before = copy.deepcopy(prices)
    first = setup.run(c, apply=True)
    second = setup.run(c, apply=True)
    assert len(c.v1.tax_rates.writes) == 2
    assert set(first['created']) == {'uk_inclusive', 'uk_exclusive'}
    assert second['created'] == [] and first['rates'] == second['rates']
    assert prices == before
    assert all(p['country'] == 'GB' and p['percentage'] == 20 for p, _ in c.v1.tax_rates.writes)


def test_reuses_existing_rates_including_later_pages():
    c, *_ = client([dict(rate('txr_other_' + str(i)), country='FR') for i in range(110)]
                   + [rate('txr_inclusive'), rate('txr_exclusive', False)])
    result = setup.run(c, apply=True)
    assert not c.v1.tax_rates.writes
    assert result['rates'] == {'uk_inclusive': 'txr_inclusive', 'uk_exclusive': 'txr_exclusive'}


@pytest.mark.parametrize('change', [dict(id='acct_wrong'), dict(company={'name': 'Different Ltd'}), dict(company={})])
def test_wrong_or_unconfirmed_company_never_mutates(change):
    c, account, *_ = client()
    account.update(change)
    with pytest.raises(setup.SetupError):
        setup.run(c, apply=True)
    assert not c.v1.tax_rates.writes


@pytest.mark.parametrize('change', [dict(unit_amount=1901), dict(tax_behavior='inclusive'),
                                  dict(livemode=False), dict(product='wrong'), dict(currency='usd')])
def test_incorrect_overseas_price_stops_before_changes(change):
    c, _, prices, *_ = client()
    prices[setup.PRICES['report_overseas'][0]].update(change)
    with pytest.raises(setup.SetupError):
        setup.run(c, apply=True)
    assert not c.v1.tax_rates.writes


def test_webhook_and_portal_must_validate_before_mutations():
    c, _, _, webhook, portal = client()
    webhook['enabled_events'].remove('checkout.session.async_payment_succeeded')
    with pytest.raises(setup.SetupError):
        setup.run(c, apply=True)
    webhook['enabled_events'] = list(setup.EVENTS)
    portal['features']['subscription_cancel']['mode'] = 'immediately'
    with pytest.raises(setup.SetupError):
        setup.run(c, apply=True)
    assert not c.v1.tax_rates.writes


@pytest.mark.parametrize('change', [dict(active=False), dict(livemode=False), dict(inclusive=False),
                                  dict(percentage=5), dict(percentage='garbled'), dict(country='FR'),
                                  dict(state='CA'), dict(display_name='Sales tax'), dict(tax_type='gst')])
def test_mismatched_tax_rate_is_never_reused(change):
    assert not setup.matches_rate(dict(rate(), **change), True)


def test_partial_failure_can_resume_without_duplicate_rate():
    c, *_ = client()
    original = c.v1.tax_rates.create
    def fail_second(params, *, options):
        if not params['inclusive']:
            raise RuntimeError('network failure')
        return original(params, options=options)
    c.v1.tax_rates.create = fail_second
    with pytest.raises(RuntimeError):
        setup.run(c, apply=True)
    c.v1.tax_rates.create = original
    setup.run(c, apply=True)
    assert len(c.v1.tax_rates.data) == 2


@pytest.mark.parametrize('secret', ['', 'rk_test_do_not_print', 'sk_test_do_not_print'])
def test_cli_rejects_test_or_missing_key_without_exposing_it(secret, monkeypatch, capsys):
    monkeypatch.setenv('STRIPE_SECRET_KEY', secret)
    assert setup.main([]) == 2
    output = capsys.readouterr().out
    assert 'error' in json.loads(output)
    assert 'do_not_print' not in output


def test_provider_errors_and_live_secret_never_reach_output(monkeypatch, capsys):
    import sys
    secret = 'rk_live_do_not_print'
    monkeypatch.setenv('STRIPE_SECRET_KEY', secret)
    monkeypatch.setitem(sys.modules, 'stripe', NS(StripeClient=lambda _: object()))
    def fail(*args, **kwargs):
        raise RuntimeError('provider response ' + secret)
    monkeypatch.setattr(setup, 'run', fail)
    assert setup.main(['--apply-uk-vat']) == 2
    output = capsys.readouterr().out
    assert secret not in output and 'provider response' not in output


def test_installed_stripe_sdk_transport_and_pagination():
    """Use the real SDK with a fake HTTP boundary; never contact live Stripe."""
    import stripe
    from urllib.parse import parse_qs, urlparse

    _, account, prices, webhook, portal = client()
    requests = []
    class Transport(stripe.HTTPClient):
        name = 'fixture'
        def request(self, method, url, headers, post_data=None, **kwargs):
            requests.append((method, url))
            parsed = urlparse(url)
            path = parsed.path
            assert method.lower() == 'get'
            if path == '/v1/account':
                data = dict(account, object='account')
            elif path.startswith('/v1/prices/'):
                data = dict(prices[path.rsplit('/', 1)[-1]], object='price')
            elif path.startswith('/v1/webhook_endpoints/'):
                data = dict(webhook, object='webhook_endpoint')
            elif path.startswith('/v1/billing_portal/configurations/'):
                data = dict(portal, object='billing_portal.configuration')
            elif path == '/v1/tax_rates':
                page_two = 'starting_after' in parse_qs(parsed.query)
                data = {'object': 'list', 'url': path, 'has_more': not page_two,
                        'data': [dict(rate('txr_exclusive', False) if page_two else rate('txr_inclusive'), object='tax_rate')]}
            else:
                raise AssertionError(path)
            return json.dumps(data), 200, {}
    sdk = stripe.StripeClient('rk_live_fixture_only', http_client=Transport())
    result = setup.run(sdk)
    assert result['rates'] == {'uk_inclusive': 'txr_inclusive', 'uk_exclusive': 'txr_exclusive'}
    assert any('starting_after=txr_inclusive' in url for _, url in requests)


def business_client(entries=()):
    c, account, *_ = client()
    data, writes = list(entries), []
    account['settings'] = {'invoices': {'default_account_tax_ids': ['txi_other_country']}}
    def create(params, *, options):
        writes.append(('create', params))
        item = dict(params, id='txi_business', livemode=True)
        data.append(item)
        return item
    def update(account_id, params):
        assert account_id == setup.ACCOUNT
        writes.append(('update', params))
        account['settings']['invoices'].update(params['settings']['invoices'])
    def listing(params):
        assert params == {'owner': {'type': 'self'}, 'limit': 100}
        return NS(auto_paging_iter=lambda: iter(data))
    c.v1.tax_ids = NS(list=listing, create=create,
                      retrieve=lambda ident: next(item for item in data if item['id'] == ident))
    c.v1.accounts.update = update
    return c, account, data, writes


def test_business_vat_default_is_read_only():
    c, _, _, writes = business_client()
    assert setup.business_vat_id(c) == {
        'tax_id': None, 'included_on_invoices': False, 'hmrc_verification_claimed': False}
    assert not writes


def test_business_vat_is_idempotent_and_preserves_invoice_defaults():
    c, account, _, writes = business_client()
    first = setup.business_vat_id(c, apply=True)
    assert setup.business_vat_id(c, apply=True) == first
    assert len(writes) == 2
    assert first['included_on_invoices'] is True
    assert account['settings']['invoices']['default_account_tax_ids'] == ['txi_other_country', 'txi_business']


def test_other_business_vat_number_is_not_overwritten():
    c, _, _, writes = business_client([{'id': 'txi_old', 'type': 'gb_vat', 'value': 'GB000000000'}])
    with pytest.raises(setup.SetupError, match='different business UK VAT'):
        setup.business_vat_id(c, apply=True)
    assert not writes


@pytest.mark.parametrize('change', [dict(livemode=False), dict(owner={'type': 'customer'}),
                                  dict(owner={'type': 'account', 'account': 'acct_wrong'})])
def test_invalid_business_tax_id_never_becomes_invoice_default(change):
    c, _, _, writes = business_client([dict(id='txi_bad', type='gb_vat', value=setup.BUSINESS_VAT_ID,
                                          livemode=True, owner={'type': 'self'}) | change])
    with pytest.raises(setup.SetupError, match='read-back validation'):
        setup.business_vat_id(c, apply=True)
    assert not writes


def test_invoice_default_failure_does_not_duplicate_business_id_on_retry():
    c, _, data, writes = business_client()
    original = c.v1.accounts.update
    def denied(*args):
        raise RuntimeError('permission denied')
    c.v1.accounts.update = denied
    with pytest.raises(RuntimeError):
        setup.business_vat_id(c, apply=True)
    c.v1.accounts.update = original
    assert setup.business_vat_id(c, apply=True)['included_on_invoices']
    assert len(data) == 1 and len(writes) == 2
