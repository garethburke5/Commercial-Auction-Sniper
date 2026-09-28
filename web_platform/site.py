"""One renderer for an ASGI website and its safe public static deployment."""
import json
import hashlib
import math
import os
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .catalogue import Catalogue, money
from .board import index_row

HERE = Path(__file__).parent
LIVE = 'https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/'

class Site:
    def __init__(self, catalogue=None, origin=None):
        self.catalogue = catalogue or Catalogue()
        self.origin = (origin or os.environ.get('PUBLIC_ORIGIN') or 'http://localhost:8000').rstrip('/')
        self.base = self.origin.split('://', 1)[-1].partition('/')[2]
        self.prefix = '/' + self.base if self.base else ''
        self.env = Environment(loader=FileSystemLoader(HERE/'templates'), autoescape=select_autoescape())
        self.env.globals.update(money=money, url=lambda p: self.prefix+p, live=LIVE)
        self.board_version = hashlib.sha256(json.dumps(self.catalogue.properties,sort_keys=True).encode()).hexdigest()[:12]
        self.env.globals.update(board_index=f'/board/{self.board_version}/index.json')

    def page(self, path, title, kind, description, **ctx):
        schema = {'@context':'https://schema.org','@type':'WebPage','name':title,'url':self.origin+path,'description':description}
        crumbs = [('Home','/')]
        if path != '/': crumbs.append((title,path))
        structured = [schema, {'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[
            {'@type':'ListItem','position':i+1,'name':label,'item':self.origin+p} for i,(label,p) in enumerate(crumbs)]}]
        return self.env.get_template('page.html').render(title=title, kind=kind, description=description,
            canonical=self.origin+path, path=path, crumbs=crumbs, catalogue=self.catalogue,
            structured=json.dumps(structured).replace('<','\\u003c'), **ctx)

    def routes(self):
        c = self.catalogue
        pages = max(1, math.ceil(len(c.properties)/50))
        yield '/', self.page('/', 'UK commercial auction properties & investment research', 'home',
            'Explore UK commercial auction property with evidenced rent, lease, guide prices and source links.',
            rows=c.properties[:50], board=True, page=1, pages=pages)
        for page in range(1,pages+1):
            path = '/properties/' if page == 1 else f'/properties/page/{page}/'
            yield path, self.page(path,'Current auction properties','list','Commercial and mixed-use lots from the published Auction Sniper catalogue.',
                rows=c.properties[(page-1)*50:page*50], page=page,pages=pages,board=True)
        for row in c.all_properties:
            yield row['path'], self.page(row['path'],row['address'],'property',
                f"{row['source']} · {row.get('property_type') or 'Auction property'} · Guide {row['guide']}.",
                row=row, history=c.history(row['address']), noindex=not row['indexable'])
        yield '/auctioneers/', self.page('/auctioneers/','Auctioneers','sources',
            'Browse the commercial and mixed-use inventory captured from UK auction houses.')
        for key,name in sorted(c.sources.items()):
            rows = [r for r in c.all_properties if r['source_slug']==key]
            yield f'/auctioneers/{key}/', self.page(f'/auctioneers/{key}/',name,'list',
                f'Published commercial and mixed-use auction properties from {name}.',rows=rows)
        events = defaultdict(list)
        for row in c.properties:
            if row.get('auction_date'): events[(row['auction_date'],row['source_slug'])].append(row)
        yield '/auctions/',self.page('/auctions/','Auction calendar','calendar',
            'Upcoming dates and retained auction outcomes, grouped by auction house.',events=sorted(events.items()))
        for (date,source),rows in events.items():
            p=f'/auctions/{source}/{date}/'
            yield p,self.page(p,f'{c.sources[source]} · {date}','list',
                'Captured commercial lots for this auction. Check the auctioneer for catalogue changes.',rows=rows)
        yield '/history/',self.page('/history/','Commercial auction history','history',
            'Individual auction appearances with source evidence. Repeated appearances are preserved.',history=c.history())
        yield '/methodology/',self.page('/methodology/','How Auction Sniper works','methodology',
            'Understand source evidence, guide prices, missing information and conservative property-history matching.')
        yield '/privacy/',self.page('/privacy/','Privacy and cookies','privacy',
            'How the public Auction Sniper website handles browsing data and external links.')
        yield '/due-diligence/',self.page('/due-diligence/','Buyer due diligence','due-diligence',
            'Read your downloaded legal-pack documents with the Auction Sniper analysis workflow.',noindex=True)

    def board_assets(self):
        """Small search index; card bundles load only for the selected results."""
        rows=self.catalogue.properties
        root=f'/board/{self.board_version}/'
        module=self.env.get_template('cards.html').module
        index=[]
        for start in range(0,len(rows),50):
            chunk=f'{start//50}.json'
            batch=rows[start:start+50]
            index.extend(index_row(row,chunk) for row in batch)
            yield root+chunk,json.dumps({r['id']:str(module.card(r)) for r in batch},ensure_ascii=False,separators=(',',':'))
        yield root+'index.json',json.dumps({'rows':index,'generated_at':self.catalogue.generated_at},ensure_ascii=False,separators=(',',':'))

    def sitemap(self, routes):
        good = {r['path'] for r in self.catalogue.all_properties if r['indexable']}
        paths = [p for p in routes if p!='/due-diligence/' and (not p.startswith('/property/') or p in good)]
        return '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(
            '<url><loc>'+escape(self.origin+p)+'</loc></url>' for p in paths)+'</urlset>'
