"""Exercise the real sandbox guard without connecting to Stripe or a database."""
import ast
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        super().__init__(detail)


source = ast.parse((Path(__file__).parents[1] / 'billing.py').read_text())
definition = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Billing')
scope = {'os': os, 'HTTPException': HTTPException}
exec(compile(ast.Module(body=[definition], type_ignores=[]), 'billing.py', 'exec'), scope)


class SandboxBillingTests(unittest.TestCase):
    def setUp(self):
        self.billing = scope['Billing'].__new__(scope['Billing'])
        self.billing.accounts = Mock()
        self.billing.accounts.is_owner.return_value = True
        self.billing.secret = 'sk_test_fixture'
        self.billing.checkout = Mock(return_value='sandbox-checkout')
        self.billing.portal = Mock(return_value='sandbox-portal')

    @patch.dict(os.environ, {'BILLING_LIVE': 'false'})
    def test_owner_reuses_checkout_and_portal(self):
        self.assertEqual(self.billing.sandbox_action('owner', 'investor'), 'sandbox-checkout')
        self.billing.checkout.assert_called_once_with('owner', 'investor')
        self.assertEqual(self.billing.sandbox_action('owner'), 'sandbox-portal')
        self.billing.portal.assert_called_once_with('owner')

    @patch.dict(os.environ, {'BILLING_LIVE': 'false'})
    def test_non_owner_cannot_start_checkout_or_portal(self):
        self.billing.accounts.is_owner.return_value = False
        for plan in ('investor', None):
            with self.assertRaises(HTTPException) as caught:
                self.billing.sandbox_action('customer', plan)
            self.assertEqual(caught.exception.status_code, 403)
        self.billing.checkout.assert_not_called()
        self.billing.portal.assert_not_called()

    @patch.dict(os.environ, {'BILLING_LIVE': 'false'})
    def test_live_or_missing_keys_rejected_before_stripe(self):
        for secret in ('sk_live_fixture', 'rk_live_fixture', ''):
            self.billing.secret = secret
            for plan in ('professional', None):
                with self.assertRaises(HTTPException) as caught:
                    self.billing.sandbox_action('owner', plan)
                self.assertEqual(caught.exception.status_code, 409)
        self.billing.checkout.assert_not_called()
        self.billing.portal.assert_not_called()

    @patch.dict(os.environ, {'BILLING_LIVE': 'true'})
    def test_live_flag_blocks_even_test_keys(self):
        with self.assertRaises(HTTPException):
            self.billing.sandbox_action('owner', 'investor')
        self.billing.checkout.assert_not_called()

    @patch.dict(os.environ, {'BILLING_LIVE': 'false'})
    def test_restricted_test_key_supported(self):
        self.billing.secret = 'rk_test_fixture'
        self.assertEqual(self.billing.sandbox_action('owner', 'professional'), 'sandbox-checkout')


if __name__ == '__main__':
    unittest.main()
