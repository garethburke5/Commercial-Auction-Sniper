"""Abandoned membership links must not remain payable after subscription activation."""
import hashlib
import hmac
import json
import time
from unittest.mock import Mock

import pytest
import stripe

from web_platform.accounts import Accounts
from web_platform.billing import Billing


@pytest.fixture
def billing(tmp_path, monkeypatch):
    accounts = Accounts(tmp_path / 'accounts.sqlite')
    accounts.ensure('alice')
    with accounts.db() as db:
        db.execute("UPDATE accounts SET customer_id='cus_a' WHERE user_id='alice'")
    b = Billing(accounts, 'sk_test_fixture', 'whsec_fixture',
                {'investor': 'price_i'}, 'https://example.org')
    b.client = Mock()
    b.client.v1.subscriptions.retrieve.return_value = {
        'id': 'sub_a', 'customer': 'cus_a', 'status': 'active',
        'items': {'data': [{'price': {'id': 'price_i'}, 'quantity': 1,
                            'current_period_end': int(time.time()) + 86400}]}}
    b.client.v1.checkout.sessions.list.return_value = {'data': [], 'has_more': False}
    monkeypatch.setenv('BILLING_LIVE', 'false')
    return b


def session(sid, **changes):
    return dict({'id': sid, 'customer': 'cus_a', 'mode': 'subscription',
                 'client_reference_id': 'alice', 'status': 'open'}, **changes)


def deliver(b, eid='evt_sub'):
    body = json.dumps({'id': eid, 'livemode': False,
        'type': 'customer.subscription.updated', 'data': {'object': {'id': 'sub_a'}}}).encode()
    ts = str(int(time.time()))
    sig = hmac.new(b'whsec_fixture', ts.encode() + b'.' + body, hashlib.sha256).hexdigest()
    return b.webhook(body, f't={ts},v1={sig}')


def test_activation_closes_only_owned_membership_links_across_pages(billing):
    sessions = billing.client.v1.checkout.sessions
    sessions.list.side_effect = [
        {'data': [session('cs_old'), session('cs_report', mode='payment'),
                  session('cs_other', client_reference_id='bob')], 'has_more': True},
        {'data': [session('cs_old2'), session('cs_foreign', customer='cus_b'),
                  session('cs_complete', status='complete')], 'has_more': False}]
    assert deliver(billing) == 'processed'
    assert [c.args[0] for c in sessions.expire.call_args_list] == ['cs_old', 'cs_old2']
    assert sessions.list.call_args.args[0]['starting_after'] == 'cs_other'
    assert deliver(billing) == 'duplicate'
    assert sessions.expire.call_count == 2
    assert billing.accounts.plan('alice') == 'investor'


def test_cleanup_failure_rolls_back_event_and_retries(billing):
    sessions = billing.client.v1.checkout.sessions
    sessions.list.return_value = {'data': [session('cs_old')], 'has_more': False}
    sessions.expire.side_effect = stripe.APIConnectionError('temporary network failure')
    with pytest.raises(stripe.APIConnectionError): deliver(billing)
    with billing.accounts.db() as db:
        assert not db.execute('SELECT 1 FROM webhook_events').fetchone()
        assert not db.execute('SELECT 1 FROM subscriptions').fetchone()
    sessions.expire.side_effect = None
    assert deliver(billing) == 'processed'
    assert billing.accounts.plan('alice') == 'investor'


@pytest.mark.parametrize('state', ['expired', 'complete'])
def test_already_closed_session_race_is_safe(billing, state):
    sessions = billing.client.v1.checkout.sessions
    sessions.list.return_value = {'data': [session('cs_old')], 'has_more': False}
    sessions.expire.side_effect = stripe.InvalidRequestError('Already closed', 'id')
    sessions.retrieve.return_value = session('cs_old', status=state)
    assert deliver(billing) == 'processed'


def test_still_open_session_error_is_not_swallowed(billing):
    sessions = billing.client.v1.checkout.sessions
    sessions.list.return_value = {'data': [session('cs_old')], 'has_more': False}
    sessions.expire.side_effect = stripe.InvalidRequestError('Cannot expire', 'id')
    sessions.retrieve.return_value = session('cs_old')
    with pytest.raises(stripe.InvalidRequestError): deliver(billing)


@pytest.mark.parametrize('state', ['incomplete', 'incomplete_expired', 'canceled'])
def test_non_active_membership_does_not_close_signup(billing, state):
    billing.client.v1.subscriptions.retrieve.return_value['status'] = state
    assert deliver(billing) == 'processed'
    billing.client.v1.checkout.sessions.list.assert_not_called()


def test_existing_subscriber_checkout_cleans_old_links_and_opens_portal(billing):
    billing.client.v1.prices.retrieve.return_value = {
        'active': True, 'currency': 'gbp', 'unit_amount': 1500,
        'recurring': {'interval': 'month', 'interval_count': 1}, 'livemode': False}
    billing.client.v1.subscriptions.list.return_value = {'data': [{'status': 'active'}]}
    billing.client.v1.checkout.sessions.list.return_value = {
        'data': [session('cs_old')], 'has_more': False}
    billing.client.v1.billing_portal.sessions.create.return_value = {'url': 'https://billing.stripe.com/example'}
    assert billing.checkout('alice', 'investor') == 'https://billing.stripe.com/example'
    billing.client.v1.checkout.sessions.expire.assert_called_once_with('cs_old')
    billing.client.v1.checkout.sessions.create.assert_not_called()
