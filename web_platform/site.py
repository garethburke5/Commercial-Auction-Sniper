"""One renderer for an ASGI website and its safe public static deployment."""
import json
import hashlib
import math
import os
from collections import defaultdict
from functools import cached_property
from pathlib import Path
from datetime import date
from urllib.parse import quote
from xml.sax.saxutils import escape
from jinja2 import Environment, FileSystemLoader, select_autoescape
from .catalogue import Catalogue, money
from .board import index_row, SEARCH_INDEX_VERSION
from .fees import load_fees, directory, fee_profile, estimate_fee
from .particulars import structured_particulars
from .enrichment import ordered_images
from .glossary import GROUPS, SOURCES, REVIEWED
from .workspace import observation

HERE = Path(__file__).parent
LIVE = 'https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/'

def uk_date(value):
    try:
        d = date.fromisoformat(str(value)[:10])
        return f'{d.day} {d:%B %Y}'
    except ValueError:
        return value or 'Date to confirm'

class Site:
    @cached_property
    def reconciliation(self):
        from source_reconciliation import reconcile
        snapshot=json.loads((self.catalogue.root/'data/properties.json').read_text())
        proof=self.catalogue.root/'data/source_live_verification.json'
        if proof.exists():
            measured=json.loads(proof.read_text())
            if measured.get('verified') and measured.get('snapshot_generated_at')==snapshot.get('generated_at'):
                return measured
        return reconcile(snapshot)
    def __init__(self, catalogue=None, origin=None):
        self.catalogue = catalogue or Catalogue()
        self.origin = (origin or os.environ.get('PUBLIC_ORIGIN') or 'http://localhost:8000').rstrip('/')
        self.base = self.origin.split('://', 1)[-1].partition('/')[2]
        self.prefix = '/' + self.base if self.base else ''
        self.env = Environment(loader=FileSystemLoader(HERE/'templates'), autoescape=select_autoescape())
        self.env.globals.update(money=money, uk_date=uk_date, url=lambda p: self.prefix+p, live=LIVE)
        from .market_context import MarketContext
        self.market=MarketContext(self.catalogue)
        self.fees = load_fees()
        self.fee_directory = directory(self.catalogue, self.fees)
        evidence_path = HERE/'property_evidence.json'
        self.evidence = json.loads(evidence_path.read_text())['properties'] if evidence_path.exists() else {}
        self.logos = {'savills-auctions':'https://www.savills.co.uk/_images/savills-square.svg',
                      'allsop-commercial':'https://assets.allsop-cdn.co.uk/build/images/packages/platform/frontend/css/logo-2f36f1d436.svg'}
        for row in getattr(self.catalogue, 'all_properties', []):
            evidence = self.evidence.get(row['url'], {})
            if evidence.get('logo_url') and 'linkedin' not in evidence['logo_url'].lower():
                self.logos.setdefault(row['source_slug'], evidence['logo_url'])
        self.env.globals['logos'] = self.logos
        # Card bundles change when their markup or deployment prefix changes,
        # even if the underlying catalogue is unchanged.
        self.board_version = hashlib.sha256(json.dumps(self.catalogue.properties,sort_keys=True).encode()
            + (HERE/'templates/cards.html').read_bytes() + self.prefix.encode()
            + str(SEARCH_INDEX_VERSION).encode()).hexdigest()[:12]
        self.env.globals['asset_version'] = hashlib.sha256((HERE/'static/site.css').read_bytes()
            + (HERE/'static/workspace.js').read_bytes() + (HERE/'static/board.js').read_bytes() + (HERE/'static/search.js').read_bytes()).hexdigest()[:12]
        self.env.globals.update(board_index=f'/board/{self.board_version}/index.json')

    def page(self, path, title, kind, description, **ctx):
        schema = {'@context':'https://schema.org','@type':'WebPage','name':title,'url':self.origin+path,'description':description}
        if kind == 'glossary':
            schema.update({'@type':'DefinedTermSet','hasDefinedTerm':[
                {'@type':'DefinedTerm','name':name,'description':definition,
                 'url':self.origin+path+'#'+term_id,'inDefinedTermSet':self.origin+path}
                for _,_,terms in GROUPS for term_id,name,definition in terms]})
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
            evidence = self.evidence.get(row['url'], {})
            detail_row = dict(row)
            if evidence.get('sections'):
                # Source section breaks improve scanning; retain the complete captured text below.
                detail_row['description'] = '\n'.join(s['title']+': '+s['text'] for s in evidence['sections'] if s.get('text'))
                # Preserve information not present in the recovered section subset.
                # The original remains in the source disclosure; structured fields fill gaps.
            gallery = ordered_images([{'url':row.get('image_url'),'label':'Auctioneer primary photograph'}] if row.get('image_url') else [], row['url'])
            if row.get('image_url'):
                gallery += ordered_images(row.get('gallery_images') or evidence.get('gallery') or [], row['url'], row.get('image_url'))
            context=self.market.for_property(row)
            yield row['path'], self.page(row['path'],row['address'],'property',
                f"{row['source']} · {row.get('property_type') or 'Auction property'} · Guide {row['guide']}.",
                row=row, history=context['history'], market=context, noindex=not row['indexable'],
                particulars=structured_particulars(detail_row), gallery=gallery,
                fee=estimate_fee(row,fee_profile(row['source_slug'],self.fees),evidence))
        yield '/auctioneers/', self.page('/auctioneers/','Auctioneers & buyer fees','sources',
            'Find your next auction. Understand the buyer fees before you bid.',auctioneers=self.fee_directory)
        for key,name in sorted(c.sources.items()):
            rows = [r for r in c.all_properties if r['source_slug']==key]
            house = next(h for h in self.fee_directory if h['slug']==key)
            yield f'/auctioneers/{key}/', self.page(f'/auctioneers/{key}/',name,'auctioneer',
                f'Commercial and mixed-use auction properties, buyer fees and source terms for {name}.',rows=rows,house=house)
        events = defaultdict(list)
        for row in c.properties:
            if row.get('auction_date'): events[(row['auction_date'],row['source_slug'])].append(row)
        yield '/auctions/',self.page('/auctions/','Auction calendar','calendar',
            'Upcoming dates and retained auction outcomes, grouped by auction house.',events=sorted(events.items()))
        for (date,source),rows in events.items():
            p=f'/auctions/{source}/{date}/'
            yield p,self.page(p,f'{c.sources[source]} · {uk_date(date)}','list',
                'Captured commercial lots for this auction. Check the auctioneer for catalogue changes.',rows=rows)
        yield '/history/',self.page('/history/','Commercial auction history','history',
            'Individual auction appearances with source evidence. Repeated appearances are preserved.',history=c.history())
        yield '/methodology/',self.page('/methodology/','How Auction Sniper works','methodology',
            'Understand source evidence, guide prices, missing information and conservative property-history matching.')
        yield '/coverage/',self.page('/coverage/','Auctioneer coverage & collection health','coverage',
            'Measured collection and publication counts. Unknown counts are shown explicitly; historical records do not substitute for current stock.',
            reconciliation=self.reconciliation,noindex=True)
        yield '/glossary/', self.page('/glossary/','Glossary of property auction terms','glossary',
            'Clear explanations of commercial property yields, leases, auction fees, legal packs, VAT and auction terminology.',
            glossary=GROUPS, glossary_sources=SOURCES, glossary_reviewed=REVIEWED)
        yield '/privacy/',self.page('/privacy/','Privacy and cookies','privacy',
            'How the public Auction Sniper website handles browsing data and external links.')
        yield '/due-diligence/',self.page('/due-diligence/','Buyer due diligence','due-diligence',
            'Review legal-pack evidence, prioritise questions for your solicitor and save a readable report.',noindex=True)
        spotlights=sorted(c.properties,key=lambda r:sum(bool(r.get(k)) for k in ('tenant','lease_expiry','tenure','annual_rent','area_sqft','image_url')),reverse=True)[:3]
        yield '/deals/',self.page('/deals/','Commercial Deals','deals','Private deals, agent opportunities and clearly labelled commercial auction spotlights.',spotlights=spotlights)
        yield '/admin/deals/',self.page('/admin/deals/','Owner listing workspace','deal-admin','Create and manage commercial property listings without editing code.',noindex=True)
        yield '/account/',self.page('/account/','My Auction Sniper','account','Your shortlist, watched properties, private notes, searches and acquisition research.',noindex=True)
        yield '/plans/',self.page('/plans/','Useful for free. Deeper when you need it.','plans',
            'Commercial auction search stays free. Explore the planned Premium tools, property reports and professional services.')

    def board_assets(self):
        """Small search index; card bundles load only for the selected results."""
        yield '/workspace-index.json',json.dumps({'rows':[observation(r) for r in self.catalogue.all_properties], 'generated_at':self.catalogue.generated_at},ensure_ascii=False)
        supabase=os.environ.get('SUPABASE_URL','')
        public_key=os.environ.get('SUPABASE_PUBLISHABLE_KEY','')
        api_origin=os.environ.get('PRIVATE_API_ORIGIN','')
        enabled=bool(supabase.startswith('https://') and public_key and api_origin.startswith('https://'))
        yield '/platform-config.json',json.dumps({'accounts_enabled':enabled,'supabase_url':supabase if enabled else None,'supabase_key':public_key if enabled else None,'api_origin':api_origin if enabled else None,'billing_enabled':os.environ.get('BILLING_LIVE')=='true' and enabled})
        yield '/source-reconciliation.json',json.dumps(self.reconciliation,ensure_ascii=False)
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
        paths = [p for p in routes if p not in ('/due-diligence/','/account/','/admin/deals/','/coverage/') and (not p.startswith('/property/') or p in good)]
        return '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(
            '<url><loc>'+escape(self.origin+p)+'</loc></url>' for p in paths)+'</urlset>'
