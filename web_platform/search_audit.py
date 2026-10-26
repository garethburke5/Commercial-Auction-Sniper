"""Validate the actual exported HTML, without claiming Google has indexed it."""
from collections import Counter, deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = set()
        self.canonical = self.description = self.robots = ''
        self.title = ''
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.add(attrs['href'])
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href', '')
        if tag == 'meta' and attrs.get('name') in ('description', 'robots'):
            setattr(self, attrs['name'], attrs.get('content', ''))
        if tag == 'title':
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False

    def handle_data(self, text):
        if self.in_title:
            self.title += text


def audit(site, routes):
    pages = {path: Page(html) for path, html in routes.items()}
    urls = {site.origin + path: path for path in routes}
    queue, reached = deque(['/']), set()
    while queue:
        path = queue.popleft()
        if path in reached or path not in pages:
            continue
        reached.add(path)
        for link in pages[path].links:
            parsed = urlsplit(urljoin(site.origin + path, link))
            target = urls.get(parsed._replace(query='', fragment='').geturl())
            if target and target not in reached:
                queue.append(target)
    sitemap = {node.text for node in ElementTree.fromstring(site.sitemap(routes)).iter()
               if node.tag.endswith('}loc')}
    failures, excluded = [], []
    for row in site.catalogue.all_properties:
        path, expected = row['path'], site.origin + row['path']
        page = pages.get(path)
        if page is None:
            failures.append({'path': path, 'problem': 'missing_page'})
            continue
        checks = {
            'incorrect_canonical': page.canonical != expected,
            'address_missing_from_title': row['address'] not in page.title,
            'address_missing_from_description': row['address'] not in page.description,
            'indexing_directive_mismatch': ('noindex' not in page.robots) != row['indexable'],
            'sitemap_mismatch': (expected in sitemap) != row['indexable'],
            'no_crawlable_path_from_home': row['indexable'] and path not in reached,
        }
        failures.extend({'path': path, 'problem': problem} for problem, failed in checks.items() if failed)
        if not row['indexable']:
            excluded.append({'path': path, 'address': row['address'], 'reasons': row['index_exclusions']})
    return {'scope': 'Rendered website checks; not Google indexing or ranking verification',
            'snapshot_generated_at': site.catalogue.generated_at,
            'property_pages': len(site.catalogue.all_properties),
            'indexable_property_pages': sum(r['indexable'] for r in site.catalogue.all_properties),
            'exclusion_counts': dict(Counter(reason for row in excluded for reason in row['reasons'])),
            'excluded_properties': excluded, 'failures': failures}
