"""Confirm the production code revision, canonical host and crawlability."""
import argparse
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from web_platform.public_config import validate_accounts


def verify(commit, origin='https://auctiongeek.co.uk', get=requests.get):
    def fetch(path):
        response = get(origin + path, timeout=(8, 30), headers={'Cache-Control': 'no-cache'})
        response.raise_for_status()
        return response

    release = fetch('/deployment.json').json()
    if release.get('commit') != commit:
        raise ValueError('Live code revision does not match the tested deployment')
    home = fetch('/')
    doc = BeautifulSoup(home.text, 'html.parser')
    canonical = doc.find('link', rel='canonical')
    if not canonical or canonical.get('href') != origin + '/':
        raise ValueError('Production canonical URL is incorrect')
    robots = doc.find('meta', attrs={'name': 'robots'})
    if 'noindex' in ((robots.get('content', '') if robots else '') + home.headers.get('X-Robots-Tag', '')).lower():
        raise ValueError('Production homepage is marked noindex')
    if origin + '/sitemap.xml' not in fetch('/robots.txt').text:
        raise ValueError('Production sitemap is not advertised')
    expected = json.loads(Path('public-dist/platform-config.json').read_text())
    validate_accounts(expected)
    if fetch('/platform-config.json').json() != expected:
        raise ValueError('Live public configuration does not match this release')
    return {'verified': True, 'commit': commit, 'origin': origin}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    for attempt in range(6):
        try:
            print(json.dumps(verify(args.commit)))
            break
        except (ValueError, requests.RequestException):
            if attempt == 5:
                raise
            time.sleep(5)
