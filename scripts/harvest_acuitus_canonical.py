"""Bounded commercial-history expansion using the established corpus contracts.

Reuse Acuitus archive discovery, bank every result-card lot (including incomplete
ones), retain status/guide/result separately, and reconcile the published count.
No lot-detail fetch is required to admit an identifiable appearance.
"""
import argparse
from collections import Counter,defaultdict
import json,re,sys,time
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from historical_acuitus import discover_auctions,fetch_auction_page,_session


def canonical_url(url):
    p=urlsplit(str(url or ''));return urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/'),'',''))

def house(value):
    v=str(value or '').lower()
    return 'allsop' if 'allsop' in v else 'acuitus' if 'acuitus' in v else v

def commercial_sector(text):
    t=(text or '').lower()
    residential=bool(re.search(r'residential|flats?|apartments?|houses?',re.sub(r'public house','pub',t)))
    commercial=bool(re.search(r'retail|office|industrial|warehouse|bank|medical|health|restaurant|pub\b|public house|hotel|leisure|shop|trade|car park|petrol|mixed|commercial|care home|nursery|storage',t))
    if 'mixed' in t or (commercial and residential):return 'mixed-use'
    if commercial:return 'commercial'
    if residential:return 'residential'
    if re.search(r'land|site|development',t):return 'land'
    return 'unknown'

def parse_results(soup,date,evidence):
    text=soup.get_text(' ',strip=True)
    match=re.search(r'(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)\s+properties',text,re.I)
    if not match:raise ValueError('Missing published result count')
    start,end,total=map(int,match.groups())
    rows=[];seen=set()
    for card in soup.select('a[href]'):
        address=card.select_one('.proplist-grid-address')
        kind=card.select_one('.proplist-sector')
        result=card.select_one('.proplist-grid-status')
        if not address or not result:continue
        pid=re.search(r'/property/(\d+)/?',card.get('href',''))
        if not pid:continue
        fields={dt.get_text(' ',strip=True).rstrip('*†').strip():dt.find_next('dd').get_text(' ',strip=True) for dt in result.find_all('dt') if dt.find_next('dd')}
        published=fields.get('Auction','')
        expected='/'.join(reversed(date.split('-')))
        if published!=expected:raise ValueError(f'Result belongs to {published}, expected {expected}')
        lot=fields.get('Lot')
        if not lot:raise ValueError('Identifiable property has no published lot number')
        source_id=pid.group(1)
        if source_id in seen:raise ValueError('Repeated source lot on result page')
        seen.add(source_id)
        url=card['href'];row=corpus.base_row('Acuitus','acuitus:'+date,date,lot,source_id,url)
        address_text=', '.join(address.stripped_strings)
        sector_text=kind.get_text(' ',strip=True) if kind else ''
        status=fields.get('Status','unknown').lower()
        row.update(address=address_text,property_type=sector_text or None,sector=commercial_sector(sector_text),
                   status=status,source_evidence=evidence,record_quality='address_record')
        if m:=corpus.PC.search(address_text):row['postcode']=m.group().upper()
        # A Guide is not a result, and undisclosed Sold Prior remains null.
        if fields.get('Price') and status in ('sold','sold prior','sold post'):
            row['sale_price']=corpus.money(fields['Price'])
        if fields.get('Guide'):
            values=re.findall(r'£[\d,]+(?:\.\d+)?',fields['Guide'])
            if values:row['guide_price']=corpus.money(values[0])
            if len(values)>1:row['guide_price_high']=corpus.money(values[1])
        img=card.find('img',src=True)
        if img:row['image_urls']=[img['src']]
        rows.append(row)
    # Current perpage=128 covers these selected catalogues. Refuse to claim a
    # paginated/changed larger catalogue complete; preserve its observed rows.
    complete=start==1 and end==total and len(rows)==total
    return rows,total,complete

class Bank:
    def __init__(self):
        self.existing={};self.locations={};self.changed=defaultdict(dict);self.added=[];self.enriched=set();self.addresses=0
        for path in (corpus.DATA/'appearances').rglob('*.jsonl.gz'):
            for row in corpus.iter_rows(path):
                self.existing[row['appearance_id']]=row
                key=(house(row['auctioneer']),row.get('auction_date'),canonical_url(row['original_url']))
                self.locations.setdefault(key,[]).append((path,row['appearance_id']))

    def admit(self,row,key):
        identity=(house(row['auctioneer']),row.get('auction_date'),canonical_url(row['original_url']))
        matches=self.locations.get(identity,[])
        if len(matches)==1:
            path,eid=matches[0];old=dict(self.existing[eid]);new=dict(old)
            for field,value in row.items():
                if field not in ('appearance_id','source_auction_id','source_lot_id','source_evidence') and new.get(field) in (None,'','unknown',[]):
                    if value not in (None,'','unknown',[]):new[field]=value
            if new!=old:
                new['additional_source_evidence']=list(old.get('additional_source_evidence',[]))+[row['source_evidence']]
                self.changed[path][eid]=new;self.existing[eid]=new;self.enriched.add(eid)
                if not old.get('address') and new.get('address'):self.addresses+=1
            return eid
        if len(matches)>1:
            # Already ambiguous duplicates remain untouched; never add another.
            return None
        if row['appearance_id'] in self.existing:return row['appearance_id']
        path=corpus.DATA/'appearances'/(key+'.jsonl.gz')
        self.changed[path][row['appearance_id']]=row;self.existing[row['appearance_id']]=row
        self.locations[identity]=[(path,row['appearance_id'])];self.added.append(row)
        return row['appearance_id']

    def flush(self):
        for path,rows in self.changed.items():
            key=str(path.relative_to(corpus.DATA/'appearances'))[:-9]
            corpus.write_rows(key,list(rows.values()))
        self.changed.clear()


def bank_saved_allsop(bank):
    """Recover previously persisted individual lots omitted by the old importer."""
    for path in sorted((corpus.ROOT/'data').glob('historical_source_corpus_allsop*.json')):
        payload=json.loads(path.read_text());rows=payload.get('lots') or payload.get('records') or []
        evidence=corpus.DATA/'sources/commercial-expansion'/('saved-'+corpus.digest(path.read_bytes())[:20]+'.json.gz')
        admitted=0
        for raw in rows:
            if 'auction' in str(raw.get('record_type','')):continue
            address=raw.get('address') or raw.get('property_address')
            date=raw.get('auction_date') or (payload.get('auction') or {}).get('auction_date')
            urls=raw.get('source_urls') or []
            url=raw.get('lot_url') or raw.get('source_url') or raw.get('url') or (urls[0] if urls else None)
            lot=raw.get('lot_number')
            if not url or not date or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(date)) or not(address or lot):continue
            if not urlsplit(url).netloc or not any(s in url for s in ('/property/','/lot/','/listings/','.pdf')):continue
            row=corpus.base_row('Allsop Commercial','allsop:'+date,date,lot,corpus.digest(canonical_url(url).encode())[:24],url)
            row.update(address=address,property_type=raw.get('property_type'),description=raw.get('description') or raw.get('notes'),
                       tenure=raw.get('tenure'),status=str(raw.get('result_status') or raw.get('result') or 'unknown').lower(),
                       guide_price=corpus.money(raw.get('guide_price_gbp') or raw.get('guide_price')),
                       sale_price=corpus.money(raw.get('result_price_gbp') or raw.get('result_price') or raw.get('sale_price')),
                       annual_rent=corpus.money(raw.get('rent_pa_gbp') or raw.get('rent_pa')),
                       record_quality='address_record' if address else 'partial_lot')
            row['sector']=commercial_sector(row['property_type'])
            if address and (m:=corpus.PC.search(address)):row['postcode']=m.group().upper()
            row['source_evidence']={'source_url':url,'source_urls':urls or [url], 'snapshot_path':str(evidence.relative_to(corpus.ROOT)),
                'origin_file':str(path.relative_to(corpus.ROOT)),'origin_sha256':corpus.digest(path.read_bytes()),'basis':'previously persisted lot evidence, not a fresh source fetch'}
            bank.admit(row,'commercial-expansion/allsop-'+date);admitted+=1
        if admitted:corpus.save_gzip(evidence,{'origin_file':str(path.relative_to(corpus.ROOT)),'payload':payload})
    bank.flush()

def harvest(year):
    baseline=json.loads((corpus.DATA/'progress.json').read_text());bank=Bank();bank_saved_allsop(bank)
    session=_session();auctions=[a for a in discover_auctions(session) if a['auction_date'].startswith(str(year)+'-')]
    if not auctions:raise ValueError('No selected historical auctions discovered')
    states=[];errors=[]
    for auction in auctions:
        date=auction['auction_date'];key='commercial-expansion/acuitus-'+date
        try:
            url,soup=fetch_auction_page(session,auction);raw=str(soup).encode()
            snapshot=corpus.DATA/'sources/commercial-expansion'/('acuitus-'+date+'-'+corpus.digest(raw)[:16]+'.json.gz')
            evidence={'source_url':url,'request_method':auction['form_method'],'request_auction_id':auction['select_value'],
                'snapshot_path':str(snapshot.relative_to(corpus.ROOT)),'sha256':corpus.digest(raw),'retrieved_at':corpus.now()}
            corpus.save_gzip(snapshot,{'evidence':evidence,'html':raw.decode()})
            rows,expected,complete=parse_results(soup,date,evidence)
            ids=[bank.admit(row,key) for row in rows];bank.flush()
            state={'auctioneer':'Acuitus','source_auction_id':'acuitus:'+date,'auction_date':date,
                'lots_captured':len(rows),'expected_public_results':expected,'catalogue_complete':complete and all(ids),
                'completion_scope':'all surviving public result-card lots; detail enrichment remains separate',
                'appearance_ids':ids,'errors':[] if complete else ['Result count/pagination not reconciled'],'checked_at':corpus.now()}
            corpus.save_json(corpus.DATA/'auctions'/(key+'.json'),state);states.append(state)
            print('BANKED',date,len(rows),'/',expected,'complete',state['catalogue_complete'],flush=True)
        except Exception as exc:
            errors.append({'auction_date':date,'error':str(exc)});print('FAILED',date,str(exc),flush=True)
        time.sleep(.3)
    report=corpus.build_database()
    delta={'baseline_total':baseline['individual_lot_records_captured'],'persisted_total':report['individual_lot_records_captured'],
        'appearances_added':len(bank.added),'added_by_sector':dict(Counter(r['sector'] for r in bank.added)),
        'added_by_auctioneer':dict(Counter(r['auctioneer'] for r in bank.added)),
        'existing_records_enriched':len(bank.enriched),'existing_addresses_recovered':bank.addresses,
        'new_records_with_address':sum(bool(r.get('address')) for r in bank.added),
        'auction_catalogues_reconciled':sum(bool(s['catalogue_complete']) for s in states),'selected_year':year,'errors':errors,
        'added_appearance_ids':[r['appearance_id'] for r in bank.added],'enriched_appearance_ids':sorted(bank.enriched),'generated_at':corpus.now()}
    corpus.save_json(corpus.DATA/'commercial_expansion.json',delta);print(json.dumps({k:v for k,v in delta.items() if not k.endswith('_ids')},indent=2),flush=True)
    if errors:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--year',type=int,default=2021);harvest(p.parse_args().year)
