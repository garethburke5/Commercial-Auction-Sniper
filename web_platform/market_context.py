"""Conservative corpus reuse: exact address history and explained comparables."""
import re,json,sqlite3
import threading
from datetime import date
from urllib.parse import urlsplit
from collections import defaultdict
from functools import cached_property

POSTCODE=re.compile(r'\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b',re.I)
def address_key(value):
    # Preserve token boundaries: 1–3 must never collide with 13 or 1/3.
    value=str(value).lower().replace('&','and').replace('–','-').replace('—','-')
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9/\-]+',' ',value)).strip()
def postcode(value):
    m=POSTCODE.search(str(value or ''));return (m.group(1).upper(),m.group(2).upper()) if m else None

def use_type(r):
    from property_summary import specialist_use
    special = specialist_use(r)
    if special:return special
    text=str(r.get('property_type') or '')+' '+str(r.get('description') or '')[:1600]
    if re.search(r'mixed[ -]use|shop (?:and|with) (?:a |\d+ )?(?:flat|residential)',text,re.I):return 'Mixed use'
    for name,pattern in [('Industrial',r'warehouse|industrial|workshop|factory'),('Retail',r'\bretail\b|\bshop\b|betting office'),('Office',r'\boffice\b'),('Hospitality',r'\bpub\b|public house|restaurant|hotel'),('Land',r'\bland\b|development site')]:
        if re.search(pattern,text,re.I):return name
    return None

def occupancy(r):
    if positive(evidenced_rent(r)):return 'Investment'
    if re.search(r'vacant',str(r.get('vacancy') or r.get('occupation') or ''),re.I):return 'Vacant'
    return None

def positive(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and v>0

def evidenced_rent(r):
    from collectors.financials import income_facts
    from collectors.core import normalize_occupation
    rent=r.get('annual_rent')
    if not positive(rent):return None
    occupation=normalize_occupation(r.get('vacancy') or r.get('occupation'),r.get('description') or '')
    if re.search(r'^vacant(?: possession)?(?: -|$)',occupation or '',re.I):return None
    facts=income_facts(r.get('description') or '')
    if not facts.get('annual_rent') and rent in [facts.get(k) for k in ('historic_rent','potential_income','erv','ground_rent')]:return None
    if str(r.get('rent_basis') or r.get('income_basis') or '').lower() in {'historic','potential','erv','estimated'}:return None
    return rent

def metrics(r):
    area=r.get('area_sqft')
    if not positive(area):
        m=re.search(r'([\d,.]+)\s*(?:sq\s*ft|sqft|ft²)',str(r.get('floor_area') or ''),re.I)
        area=float(m.group(1).replace(',','')) if m else None
    rent=evidenced_rent(r);guide=r.get('guide_price');high=r.get('guide_price_high') or r.get('guide_price_upper')
    sale=r.get('sale_price');status=str(r.get('status') or '').lower().replace(' ','_')
    actual_sale=status in {'sold','sold_prior','sold_after','sold_at_auction'}
    return {'sale_giy':round(100*rent/sale,2) if actual_sale and positive(sale) and positive(rent) else None,'evidenced_rent':rent,'area_sqft':area,'guide_psf':round(guide/area,2) if positive(guide) and positive(area) else None,
        'rent_psf':round(rent/area,2) if positive(rent) and positive(area) and occupancy(r)=='Investment' else None,
        'giy':round(100*rent/(high or guide),2) if positive(rent) and positive(guide) and occupancy(r)=='Investment' else None}

class MarketContext:
    def __init__(self,catalogue):
        self.c=catalogue;self.by_address=defaultdict(list);self.by_district=defaultdict(list);self.loaded=False;self.observed=defaultdict(list)
        self._load_lock=threading.Lock()
    def load(self):
        with self._load_lock:
            if self.loaded:return
            self.by_address.clear();self.by_district.clear();self.observed.clear()
            self._load()
            self.loaded=True

    def _load(self):
        observations_path=self.c.root/'data/property_history.json'
        if observations_path.exists():
            import ijson
            with observations_path.open('rb') as source:
                for event in ijson.items(source,'auction_events.item',use_float=True):
                    address=event.get('address_as_published') or ''
                    if postcode(address):
                        compact={k:event.get(k) for k in ('address_as_published','tenure','source')}
                        compact['source_evidence']={'listing_url':(event.get('source_evidence') or {}).get('listing_url')}
                        compact['observations']=[{k:o.get(k) for k in ('observed_at','guide_price','annual_rent','tenant','lease_term','occupation','status')} for o in event.get('observations') or []]
                        self.observed[address_key(address)].append(compact)
        self.c.history(limit=1)
        if not self.c.history_path:return
        with sqlite3.connect(self.c.history_path.as_uri()+'?mode=ro',uri=True) as db:
            for rowid,raw in db.execute("SELECT rowid,record_json FROM appearances WHERE sector IN ('commercial','mixed-use') AND address IS NOT NULL AND auction_date<=?",(date.today().isoformat(),)):
                r=json.loads(raw);p=postcode(r.get('postcode') or r['address'])
                if not p:continue
                self.by_address[address_key(r['address'])].append(rowid)
                if positive(r.get('guide_price')) or positive(r.get('sale_price')):
                    self.by_district[p[0]].append(rowid)

    def _records(self,refs):
        if not refs:return
        # In-memory fixture contexts retain the same public matching contract.
        if isinstance(refs[0],dict):
            yield from refs;return
        with sqlite3.connect(self.c.history_path.as_uri()+'?mode=ro',uri=True) as db:
            for start in range(0,len(refs),400):
                batch=refs[start:start+400]
                for raw, in db.execute('SELECT record_json FROM appearances WHERE rowid IN ('+','.join('?' for _ in batch)+') ORDER BY rowid',batch):
                    yield json.loads(raw)
    def for_property(self,row,limit=4):
        self.load();key=address_key(row['address']);p=postcode(row['address']);typ=use_type(row);occ=occupancy(row)
        history=[];appearance_keys=set()
        for r in self._records(self.by_address.get(key,[])):
            if not p or postcode(r.get('postcode') or r['address'])!=p:continue
            if r.get('tenure') and row.get('tenure') and r['tenure'].lower()!=row['tenure'].lower():continue
            historical_url=urlsplit(str(r.get('original_url') or ''))
            current_url=urlsplit(str(row.get('url') or ''))
            same_source=historical_url.netloc and (historical_url.netloc.lower(),historical_url.path.rstrip('/')) == (current_url.netloc.lower(),current_url.path.rstrip('/'))
            try:near_date=abs((date.fromisoformat(str(r.get('auction_date'))[:10])-date.fromisoformat(str(row.get('auction_date'))[:10])).days)<=14
            except ValueError:near_date=False
            if same_source and near_date and str(r.get('lot_number','')).removeprefix('Lot ')==str(row.get('lot_number','')).removeprefix('Lot '):
                # A small date correction is not a new auction appearance.
                # URLs reused in later years must still retain earlier appearances.
                continue
            if r.get('auction_date')==row.get('auction_date') and str(r.get('lot_number','')).removeprefix('Lot ')==str(row.get('lot_number','')).removeprefix('Lot '):continue
            appearance=(r.get('auctioneer') or r.get('source'),r.get('auction_date'),str(r.get('lot_number') or ''),address_key(r['address']))
            if appearance in appearance_keys:continue
            appearance_keys.add(appearance)
            record=dict(r)
            record['comparison_notes']=[]
            before,after=metrics(r)['area_sqft'],metrics(row)['area_sqft']
            if before and after and abs(before-after)/max(before,after)>0.05:
                record['comparison_notes'].append('The recorded floor area differs from this listing. The units or extent may have changed; prices may not be directly comparable.')
            if not r.get('tenure'):
                record['comparison_notes'].append('Tenure was not recorded for this appearance. Confirm that it covers the same property interest.')
            history.append(record)
            history.sort(key=lambda x:x.get('auction_date') or '',reverse=True)
            del history[101:]
        history.sort(key=lambda x:x.get('auction_date') or '',reverse=True)
        for i,r in enumerate(history[:-1]):
            prev=history[i+1];r['changes']=[]
            for field,label in [('guide_price','Guide'),('annual_rent','Rent'),('tenant','Tenant'),('lease_expiry','Lease expiry'),('vacancy','Occupation')]:
                if r.get(field) is not None and prev.get(field) is not None and r[field]!=prev[field]:r['changes'].append({'label':label,'before':prev[field],'after':r[field]})
        candidates={};seen=set()
        for r in self._records(self.by_district.get(p[0],[])) if p and typ else []:
            if address_key(r['address'])==key or use_type(r)!=typ:continue
            if not occ or occupancy(r)!=occ:continue
            if r.get('tenure') and row.get('tenure') and r['tenure'].lower()!=row['tenure'].lower():continue
            try:age=(date.today()-date.fromisoformat(r['auction_date'][:10])).days
            except ValueError:continue
            if age>5*366 or age<0:continue
            score=10-age/366;why=[f'{typ} in the same postcode district ({p[0]})',f'{occ.lower()} property']
            if r.get('tenure') and row.get('tenure'):score+=2;why.append(r['tenure'])
            a=metrics(row)['area_sqft'];b=metrics(r)['area_sqft']
            if a and b:
                if max(a,b)/min(a,b)>2:continue
                score+=2;why.append('Recorded floor area within 2× the subject')
            if r.get('tenant') and row.get('tenant') and address_key(r['tenant'])==address_key(row['tenant']):score+=3;why.append('Same named tenant; covenant not independently rated')
            differences=[]
            for field,label in [('tenant','Tenant'),('lease_expiry','Lease expiry'),('break_clause','Break clause'),('annual_rent','Passing rent'),('occupation','Occupation')]:
                if r.get(field) is not None and row.get(field) is not None and str(r[field]).lower()!=str(row[field]).lower():
                    differences.append({'label':label,'then':r[field],'now':row[field]})
            r=dict(r,why=why,differences=differences,comparison_metrics=metrics(r))
            candidate_key=address_key(r['address'])
            if candidate_key not in candidates or score>candidates[candidate_key][0]:
                candidates.pop(candidate_key,None)
                candidates[candidate_key]=(score,r)
                if len(candidates)>limit:
                    # Stable ties retain the earlier record, as the full sort did.
                    lowest=min(v[0] for v in candidates.values())
                    drop=next(k for k in reversed(candidates) if candidates[k][0]==lowest)
                    del candidates[drop]
        selected=[]
        for _,r in sorted(candidates.values(),key=lambda v:v[0],reverse=True):
            k=address_key(r['address'])
            if k in seen:continue
            seen.add(k);selected.append(r)
            if len(selected)>=limit:break
        return {'observations':self.observations(row),'history':history[:100],'comparables':selected,'metrics':metrics(row),'matching':'Exact full address and postcode; contradictory tenures excluded. Extent remains subject to source verification.'}

    def observations(self,row):
        """Use already banked source observations; a capture date is not a sale date."""
        result=[];seen=set()
        fields=[('guide_price','Guide price'),('annual_rent','Recorded annual rent'),('tenant','Tenant'),
                ('lease_term','Lease term'),('occupation','Occupation'),('status','Status')]
        for event in self.observed.get(address_key(row['address']),[]):
            if postcode(event.get('address_as_published'))!=postcode(row['address']):continue
            if event.get('tenure') and row.get('tenure') and event['tenure'].lower()!=row['tenure'].lower():continue
            evidence=event.get('source_evidence') or {};url=evidence.get('listing_url')
            if not url or not url.startswith(('https://','http://')):continue
            observations=sorted(event.get('observations') or [],key=lambda x:x.get('observed_at') or '')
            for previous,current in zip(observations,observations[1:]):
                changes=[]
                for field,label in fields:
                    before=previous.get(field);after=current.get(field)
                    if before not in (None,'') and after not in (None,'') and before!=after:
                        changes.append({'label':label,'before':before,'after':after})
                if not changes:continue
                key=(url,current.get('observed_at'),json.dumps(changes,sort_keys=True))
                if key in seen:continue
                seen.add(key);result.append({'source':event.get('source'),'url':url,
                    'observed_at':current.get('observed_at'),'changes':changes})
        return sorted(result,key=lambda x:x['observed_at'] or '',reverse=True)[:40]
