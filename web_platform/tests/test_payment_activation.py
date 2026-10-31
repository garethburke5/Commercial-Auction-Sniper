"""Launch must not expose sandbox checkout or bypass report delivery checks."""
import pytest
from fastapi import HTTPException
from web_platform.billing import Billing
from web_platform.payment_availability import availability
from acquisition_quality import paid_report_status, evidence_sufficiency


def live_config():
    return {
        'BILLING_LIVE':'true', 'PAID_REPORTS_ENABLED':'true',
        'BILLING_TAX_MODE':'not_registered',
        'STRIPE_SECRET_KEY':'rk_live_fixture', 'STRIPE_WEBHOOK_SECRET':'whsec_fixture',
        'PUBLIC_ORIGIN':'https://auctiongeek.co.uk',
        **{key:'price_fixture' for key in (
            'STRIPE_PRICE_INVESTOR','STRIPE_PRICE_PROFESSIONAL','STRIPE_PRICE_LEGAL_PACK_REPORT',
            'STRIPE_PRICE_REPORT_INVESTOR','STRIPE_PRICE_REPORT_PROFESSIONAL',
            'STRIPE_PRICE_PROPERTY_HISTORY','STRIPE_PRICE_HISTORY_DAY_PASS')},
        'HISTORY_SALES_ENABLED':'true','HISTORY_ARCHIVE_PRIVATE':'true',
        'HISTORY_QUALITY_APPROVED':'true','HISTORY_TAX_MODE':'not_registered'}


@pytest.mark.parametrize('secret', ['', 'sk_test_fixture', 'rk_test_fixture'])
def test_live_flag_cannot_open_test_or_missing_credentials(secret, monkeypatch):
    env=live_config();env['STRIPE_SECRET_KEY']=secret
    assert not any(availability(env).values())
    monkeypatch.setenv('BILLING_LIVE','true')
    billing=Billing.__new__(Billing)
    billing.secret=secret;billing.webhook_secret='whsec_fixture';billing.origin=env['PUBLIC_ORIGIN']
    with pytest.raises(HTTPException):billing.configured()


def test_product_controls_and_missing_prices_are_independent():
    env=live_config();assert all(availability(env).values())
    env.pop('STRIPE_PRICE_REPORT_PROFESSIONAL')
    state=availability(env)
    assert state['membership_checkout_available'] and state['history_checkout_available']
    assert not state['report_checkout_available']
    env['HISTORY_ARCHIVE_PRIVATE']='false'
    assert not availability(env)['history_checkout_available']
    env['BILLING_LIVE']='false'
    assert not any(v for k,v in availability(env).items() if k.endswith('_available'))


def test_inclusive_tax_requires_configured_rate():
    env=live_config();env['HISTORY_TAX_MODE']='inclusive_manual'
    assert not availability(env)['history_checkout_available']
    env['HISTORY_STRIPE_TAX_RATE']='txr_fixture'
    assert availability(env)['history_checkout_available']
    env['BILLING_TAX_MODE']='inclusive_manual'
    assert not availability(env)['membership_checkout_available']
    assert not availability(env)['report_checkout_available']
    env['STRIPE_TAX_RATE']='txr_fixture'
    assert availability(env)['membership_checkout_available']
    assert availability(env)['report_checkout_available']


@pytest.mark.parametrize('changes', [{'inclusive':False}, {'active':False}, {'livemode':False}])
def test_live_vat_rejects_exclusive_inactive_or_test_rate(monkeypatch,changes):
    from types import SimpleNamespace
    monkeypatch.setenv('BILLING_TAX_MODE','inclusive_manual')
    monkeypatch.setenv('STRIPE_TAX_RATE','txr_fixture')
    billing=Billing.__new__(Billing);billing.secret='rk_live_fixture'
    rate={'active':True,'inclusive':True,'livemode':True}
    billing.client=SimpleNamespace(v1=SimpleNamespace(tax_rates=SimpleNamespace(retrieve=lambda _:rate)))
    assert billing._tax_rates()==['txr_fixture']
    rate.update(changes)
    with pytest.raises(HTTPException):billing._tax_rates()


def test_owner_release_does_not_approve_insufficient_report(monkeypatch):
    monkeypatch.delenv('PAID_REPORTS_ENABLED',raising=False)
    assert not paid_report_status()['purchase_available']
    monkeypatch.setenv('PAID_REPORTS_ENABLED','true')
    assert paid_report_status()['purchase_available']
    assert not evidence_sufficiency({})['charge_eligible']
    monkeypatch.setenv('PAID_REPORTS_ENABLED','false')
    assert not paid_report_status()['purchase_available']
