import pytest
from web_platform.public_config import account_config, PRODUCTION_ORIGINS


@pytest.mark.parametrize('origin', sorted(PRODUCTION_ORIGINS))
def test_empty_actions_variables_keep_production_accounts_enabled(origin):
    config = account_config(origin, {'SUPABASE_URL':'', 'SUPABASE_PUBLISHABLE_KEY':'', 'PRIVATE_API_ORIGIN':''})
    assert config['accounts_enabled']
    assert config['supabase_url'] == 'https://axoukcujpxkfvocwuaqg.supabase.co'
    assert config['supabase_key'].startswith('sb_publishable_')
    assert not config['billing_enabled']


def test_unconfigured_local_preview_does_not_connect_to_production():
    assert not account_config('http://localhost:8000', {})['accounts_enabled']


def test_partial_override_cannot_mix_projects_or_silently_disable_accounts():
    with pytest.raises(ValueError, match='disabled'):
        account_config('https://auctiongeek.co.uk', {'SUPABASE_URL':'https://another.example'})


@pytest.mark.parametrize('key', ['sb_secret_private', 'eyJ.service_role.jwt', ''])
def test_server_credentials_never_exported(key):
    with pytest.raises(ValueError):
        account_config('https://auctiongeek.co.uk', {
            'SUPABASE_URL':'https://auth.example', 'SUPABASE_PUBLISHABLE_KEY':key,
            'PRIVATE_API_ORIGIN':'https://api.example'})


def test_complete_public_override_still_supported():
    config = account_config('https://auctiongeek.co.uk', {
        'SUPABASE_URL':'https://auth.example', 'SUPABASE_PUBLISHABLE_KEY':'sb_publishable_test',
        'PRIVATE_API_ORIGIN':'https://api.example', 'BILLING_LIVE':'true'})
    assert config['supabase_url'] == 'https://auth.example'
    assert config['billing_enabled']
