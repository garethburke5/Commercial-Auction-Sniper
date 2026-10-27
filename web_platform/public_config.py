"""Browser-safe account settings, independent of optional Actions variables.

The checked-in key is a Supabase publishable key, not a server credential.
Billing and paid-report activation remain separate, explicit gates.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

PRODUCTION_ORIGINS = {
    'https://auctiongeek.co.uk',
    'https://garethburke5.github.io/Commercial-Auction-Sniper',
}
FIELDS = {
    'supabase_url': 'SUPABASE_URL',
    'supabase_key': 'SUPABASE_PUBLISHABLE_KEY',
    'api_origin': 'PRIVATE_API_ORIGIN',
}


def validate_accounts(config):
    if config.get('accounts_enabled') is not True:
        raise ValueError('Production account configuration is disabled')
    for field in ('supabase_url', 'api_origin'):
        url = urlsplit(config.get(field) or '')
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path not in ('', '/') or url.query or url.fragment):
            raise ValueError('Account configuration requires HTTPS service origins')
    # Publishable keys are intentionally public. Never export secret or JWT
    # service-role credentials even if a build variable is set incorrectly.
    if not str(config.get('supabase_key', '')).startswith('sb_publishable_'):
        raise ValueError('Account configuration requires a Supabase publishable key')


def account_config(origin, environ=None):
    env = os.environ if environ is None else environ
    values = {field: env.get(variable, '').strip() for field, variable in FIELDS.items()}
    production = origin.rstrip('/') in PRODUCTION_ORIGINS
    if production and not any(values.values()):
        values = json.loads(Path(__file__).with_name('public-account-config.json').read_text())
    enabled = all(values.values())
    config = {'accounts_enabled': enabled,
              **{key: value if enabled else None for key, value in values.items()},
              'billing_enabled': enabled and env.get('BILLING_LIVE') == 'true',
              'share_analytics_endpoint': values['api_origin'].rstrip('/') + '/api/share-events'
                  if values['api_origin'].startswith('https://') else None}
    if production or enabled:
        validate_accounts(config)
    return config
