"""Conservative corpus reuse: exact address history and explained comparables."""
import re,json,sqlite3
from datetime import date
from collections import defaultdict
from functools import cached_property

POSTCODE=re.compile(r'\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b',re.I)
def address_key(value):return re.sub(r'[^a-z0-9]','',str(value).lower().replace('&','and'))
def postcode(value):
    m=POSTCODE.search(str(value or ''));return (m.group(1).upper(),m.group(2).upper()) if m else None

def use_type(r):
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
    def __init__(self,catalogue):self.c=catalogue;self.by_address=defaultdict(list);self.by_district=defaultdict(list);self.loaded=False;self.observed=defaultdict(list)
    def load(self):
        if self.loaded:return
        self.loaded=True
        observations_path=self.c.root/'data/property_history.json'
        if observations_path.exists():
            for event in json.loads(observations_path.read_text()).get('auction_events',[]):
                address=event.get('address_as_published') or ''
                if postcode(address):self.observed[address_key(address)].append(event)
        self.c.history(limit=1)
        if not self.c.history_path:return
        with sqlite3.connect(self.c.history_path.as_uri()+'?mode=ro',uri=True) as db:
            for raw, in db.execute("SELECT record_json FROM appearances WHERE sector IN ('commercial','mixed-use') AND address IS NOT NULL AND auction_date<=?",(date.today().isoformat(),)):
                r=json.loads(raw);p=postcode(r.get('postcode') or r['address'])
                if not p:continue
                self.by_address[address_key(r['address'])].append(r)
                if positive(r.get('guide_price')) or positive(r.get('sale_price')):
                    self.by_district[p[0]].append(r)
    def for_property(self,row,limit=4):
        self.load();key=address_key(row['address']);p=postcode(row['address']);typ=use_type(row);occ=occupancy(row)
        history=[]
        for r in self.by_address.get(key,[]):
            if not p or postcode(r.get('postcode') or r['address'])!=p:continue
            if r.get('tenure') and row.get('tenure') and r['tenure'].lower()!=row['tenure'].lower():continue
            if r.get('auction_date')==row.get('auction_date') and str(r.get('lot_number','')).removeprefix('Lot ')==str(row.get('lot_number','')).removeprefix('Lot '):continue
            history.append(dict(r))
        history.sort(key=lambda x:x.get('auction_date') or '',reverse=True)
        for i,r in enumerate(history[:-1]):
            prev=history[i+1];r['changes']=[]
            for field,label in [('guide_price','Guide'),('annual_rent','Rent'),('tenant','Tenant'),('lease_expiry','Lease expiry'),('vacancy','Occupation')]:
                if r.get(field) is not None and prev.get(field) is not None and r[field]!=prev[field]:r['changes'].append({'label':label,'before':prev[field],'after':r[field]})
        candidates=[];seen=set()
        for r in self.by_district.get(p[0],[]) if p and typ else []:
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
            r=dict(r,why=why,differences=differences,comparison_metrics=metrics(r));candidates.append((score,r))
        selected=[]
        for _,r in sorted(candidates,key=lambda v:v[0],reverse=True):
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
