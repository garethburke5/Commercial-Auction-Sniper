"""Bounded public-catalogue collection with per-lot reconciliation evidence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import re
import requests
from bs4 import BeautifulSoup
from .core import SourceResult, norm
from .publication_quality import commercial_decision

HEADERS = {'User-Agent': 'AuctionGeek/1.0 (public property catalogue research)'}

def fetch(url):
    r=requests.get(url,headers=HEADERS,timeout=(10,35));r.raise_for_status()
    return BeautifulSoup(r.content,'lxml')

def published_date(text):
    m=re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})\b',text or '',re.I)
    if m:
        for fmt in ('%d %B %Y','%d %b %Y'):
            try:return datetime.strptime(' '.join(m.groups()),fmt).date().isoformat()
            except ValueError:pass
    m=re.search(r'\b(\d{2})/(\d{2})/(20\d{2})\b',text or '')
    if m:
        try:return datetime.strptime(m[0],'%d/%m/%Y').date().isoformat()
        except ValueError:pass
    return None

def outcome(text):
    """Only an outcome field/card summary; never whole-page sale conditions."""
    t=re.sub(r'unless sold (?:prior|before)|(?:may|can|could) be sold (?:prior|before)','',norm(text),flags=re.I)
    for p,status in [(r'\b(?:unsold|not sold|reserve not met)\b','UNSOLD'),(r'\bwithdrawn\b','WITHDRAWN'),(r'\bpostponed\b','POSTPONED'),(r'\bsold (?:prior|before)\b','SOLD PRIOR'),(r'\bsold (?:after|post)\b','SOLD AFTER'),(r'\bsold\b','SOLD')]:
        if re.search(p,t,re.I):
            m=re.search(r'\bsold(?:\s+for|\s*@(?:\s*auction)?)?\s*£\s*([\d,]+(?:\.\d+)?)',t,re.I) if status.startswith('SOLD') else None
            return status,float(m[1].replace(',','')) if m else None
    return 'CURRENT',None

def hydrate(source,seeds,parser,*,fetcher=None,expected=None,pages=(),errors=(),scope='Published catalogue',today=None,classifier=None):
    fetcher=fetcher or fetch;today=today or date.today();errors=list(errors);lots=[];records=[]
    def one(item):
        url,seed=item
        try:
            lot=parser(url,seed,fetcher(url));lot.finalise();decision=(classifier or commercial_decision)(lot.to_dict())
            return lot,{'url':url,'auction_date':lot.auction_date,'status':lot.status,'commercial':decision,
                'address':lot.address,'guide_price':lot.guide_price,'annual_rent':lot.annual_rent,
                'has_image':bool(lot.image_url),'tenure':lot.tenure,
                'outcome':'commercial/mixed-use' if decision else 'residential' if decision is False else 'commercial use not established'}
        except Exception as e:return None,{'url':url,'outcome':'detail failure','error':type(e).__name__+': '+str(e)[:200]}
    for lot,record in ThreadPoolExecutor(max_workers=3).map(one,seeds.items()):
        records.append(record)
        if lot is None:errors.append(record['url']+': '+record['error'])
        elif record['commercial'] is True:lots.append(lot)
    complete=expected is not None and len(seeds)==expected and not errors
    if expected is not None and len(seeds)!=expected:errors.append(f'Catalogue contains {expected} lots; {len(seeds)} unique links captured')
    current=[l for l in lots if not l.auction_date or l.auction_date>=today.isoformat()]
    classified=all(r.get('commercial') is not None for r in records)
    t={'scope':scope,'source_lot_count':expected,'discovered_lot_urls':len(seeds),
       'detail_pages_inspected':sum(r['outcome']!='detail failure' for r in records),
       'commercial_mixed_candidates':len(current),'commercial_records_including_results':len(lots),
       'classification_rejections':sum(r.get('commercial') is not True and r['outcome']!='detail failure' for r in records),
       'past_auction_exclusions':sum(bool(l.auction_date and l.auction_date<today.isoformat()) for l in lots),
       'unknown_auction_date_lots':sum(not l.auction_date for l in lots),
       'catalogue_complete':complete if expected is not None else None,
       'commercial_inventory_complete':complete and classified,
       'unclassified_lots':sum(r.get('commercial') is None for r in records), 'discovery_failures':errors,
       'catalogue_pages':list(pages),'lot_outcomes':records,'current_catalogue_detected':bool(current),
       'source_commercial_urls':[l.url for l in lots] if complete and classified else None,
       'source_observed_at':datetime.now(timezone.utc).isoformat()}
    return SourceResult(source,'DEGRADED' if errors else 'LIVE',lots,
        f'{len(seeds)} catalogue links; {t["detail_pages_inspected"]} details parsed; {len(lots)} commercial/mixed-use records, including {len(lots)-len(current)} past appearances. '+('Published total reconciled. ' if complete else 'Whole-catalogue completeness unverified. ')+'; '.join(errors[:3]),
        discovered_count=len(seeds),authoritative_snapshot=False,scope_dates=tuple(sorted({l.auction_date for l in lots if l.auction_date})),reconciliation=t)

def failed(source,url,error):
    return SourceResult(source,'DEGRADED',[],f'Catalogue could not be collected: {error}',reconciliation={'catalogue_pages':[url],'catalogue_complete':False,'source_lot_count':None,'discovery_failures':[str(error)]})


def inventory_evidence(lots, complete, scope):
    """Expose exact URL/date pairs only after the caller reconciles its source."""
    return {'commercial_inventory_complete':bool(complete),'scope':scope,
        'source_commercial_urls':[lot.url for lot in lots] if complete else None,
        'commercial_lot_evidence':[{'url':l.url,'auction_date':l.auction_date,'commercial':True,'status':l.status} for l in lots]}
