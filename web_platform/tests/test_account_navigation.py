"""Shared navigation rendering and existing Supabase session event integration."""
import subprocess
from pathlib import Path
from bs4 import BeautifulSoup
from web_platform.tests.test_platform import site


def test_account_navigation_defaults_to_sign_in_on_all_pages(site):
    for path, html in site.routes():
        soup = BeautifulSoup(html, 'html.parser')
        nav = soup.select_one('#main-navigation')
        account = nav.select_one('[data-account-link]')
        assert account.get_text() == 'Sign in / Register'
        assert account['href'].endswith('/account/')
        sign_out = nav.select_one('button[data-sign-out]')
        assert sign_out.get_text() == 'Sign Out'
        assert 'hidden' in sign_out.attrs and sign_out['type'] == 'button'
        assert soup.select_one('.nav-toggle')['aria-controls'] == nav['id']
        if path == '/account/':
            assert soup.h1.get_text() == 'My Auction Geek'
            assert account['aria-current'] == 'page'
            assert soup.select_one('#account-signout').has_attr('data-sign-out')


def test_supabase_session_navigation_transitions():
    subprocess.run(['node', '--test', str(Path(__file__).with_name('account_navigation.cjs'))], check=True)
