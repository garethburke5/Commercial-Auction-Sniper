"""Discover and bank all retained dated Barnard Marcus catalogues, all sectors."""
from datetime import datetime,date
from pathlib import Path
import argparse,json,re,sys
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_barnard_marcus import BASE,fetch_text,harvest,recover_sitemap_rows


def discover(text,today=None):
    today=today or date.today();found={}
    for url in re.findall(r'https://www\.barnardmarcusauctions\.co\.uk/auctions/\d{1,2}-[a-z]+-\d{4}/',text,re.I):
        try:day=datetime.strptime(urlparse(url).path.strip('/').split('/')[1],'%d-%B-%Y').date()
        except ValueError:continue
        if day<=today:found[day.isoformat()]=url
    return sorted(found.items())


def reconciled(payload):
    rows=payload.get('lot_records') or []
    ids=[r.get('source_record_id') for r in rows]
    # Earlier captures used lot_enumeration_complete. Respect their retained
    # reconciliation evidence rather than repeatedly re-fetching old catalogues.
    return bool(rows and (payload.get('catalogue_complete') or payload.get('lot_enumeration_complete'))
                and len(rows)==payload.get('published_rows')==payload.get('source_reported_rows')
                and all(ids) and len(set(ids))==len(ids))


def run(limit=4):
    index=BASE+'/sitemap.xml';raw=fetch_text(index)
    auctions=discover(raw)
    if not auctions:raise ValueError('No retained dated catalogues discovered')
    root=corpus.ROOT/'data/historical_source_corpus';root.mkdir(parents=True,exist_ok=True)
    snapshot=corpus.DATA/'sources/barnard-marcus'/('sitemap-'+corpus.digest(raw.encode())[:16]+'.json.gz')
    corpus.save_gzip(snapshot,{'source_url':index,'retrieved_at':corpus.now(),'xml':raw})
    attempted=[];failures=[];captured=0;reconciled_saved=[]
    # Uncaptured catalogues first; then repair previously partial captures.
    ordered=sorted(auctions,key=lambda item:((root/('barnard_marcus_'+item[0].replace('-','_')+'.json')).exists(),item[0]))
    for day,url in ordered:
        path=root/('barnard_marcus_'+day.replace('-','_')+'.json')
        prior=json.loads(path.read_text()) if path.exists() else {}
        if reconciled(prior):continue
        # Repair already-banked rows against the live sitemap identity inventory
        # before spending the bounded run on unstable SearchApi pagination.
        # This can only promote a catalogue when its exact unique property-ID set
        # equals every retained first-party lot URL for that auction.
        if prior.get('lot_records'):
            urls=sitemap_lot_urls_from_xml(url,raw)
            prior=recover_sitemap_rows(prior,lot_urls=urls)
            if reconciled(prior):
                prior['captured_at']=corpus.now();prior['discovery_evidence']=str(snapshot.relative_to(corpus.ROOT))
                corpus.save_json(path,prior)
                corpus.bank_source_corpus()
                reconciled_saved.append(day)
                print(f'Barnard Marcus: reconciled {len(prior["lot_records"])} saved rows for {day} from exact sitemap identities',flush=True)
                continue
        if len(attempted)>=limit:break
        attempted.append(day)
        print(f'Barnard Marcus: collecting {day} from {url}',flush=True)
        try:
            payload=harvest(url,day,workers=2,allow_incomplete=True,
                            cache_dir=corpus.DATA/"sources/barnard-marcus/api-pages"/day)
            payload=recover_sitemap_rows(payload,lot_urls=sitemap_lot_urls_from_xml(url,raw))
            payload['captured_at']=corpus.now();payload['discovery_evidence']=str(snapshot.relative_to(corpus.ROOT))
            corpus.save_json(path,payload)
            # Persist the individual lots immediately; a later timeout must not
            # leave only a catalogue shell or unbanked temporary JSON behind.
            corpus.bank_source_corpus()
            captured+=len(payload['lot_records'])
            print(f'Barnard Marcus: banked {len(payload["lot_records"])} rows for {day}',flush=True)
        except Exception as exc:failures.append({'auction_date':day,'url':url,'error':str(exc)[:600]})
    remaining=[]
    for day,url in auctions:
        p=root/('barnard_marcus_'+day.replace('-','_')+'.json')
        s=json.loads(p.read_text()) if p.exists() else {}
        if not reconciled(s):remaining.append({'date':day,'url':url})
    result={'checked_at':corpus.now(),'catalogues_discovered':len(auctions),'catalogues_attempted':attempted,
            'lot_rows_captured_this_run':captured,'remaining_catalogues':remaining,'failures':failures,
            'catalogues_reconciled_from_saved_rows':reconciled_saved,
            'complete':not remaining and not failures,'completion_scope':'Retained official sitemap catalogues only; not a claim of twenty-year completeness'}
    corpus.save_json(corpus.DATA/'barnard_marcus_collection.json',result)
    print(json.dumps(result,indent=2))
    return result


def sitemap_lot_urls_from_xml(page_url,text):
    """Parse one auction's exact detail inventory from the already-fetched sitemap."""
    from scripts.harvest_barnard_marcus import sitemap_lot_urls
    return sitemap_lot_urls(page_url,sitemap_text=text)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=4)
    s=run(p.parse_args().limit)
    if s['failures']:raise SystemExit(1)
