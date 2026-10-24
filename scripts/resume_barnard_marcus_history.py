"""Discover and bank all retained dated Barnard Marcus catalogues, all sectors."""
from datetime import datetime,date
from pathlib import Path
import argparse,json,re,sys
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus
from scripts.harvest_barnard_marcus import BASE,fetch_text,harvest


def discover(text,today=None):
    today=today or date.today();found={}
    for url in re.findall(r'https://www\.barnardmarcusauctions\.co\.uk/auctions/\d{1,2}-[a-z]+-\d{4}/',text,re.I):
        try:day=datetime.strptime(urlparse(url).path.strip('/').split('/')[1],'%d-%B-%Y').date()
        except ValueError:continue
        if day<=today:found[day.isoformat()]=url
    return sorted(found.items())


def run(limit=4):
    index=BASE+'/sitemap.xml';raw=fetch_text(index)
    auctions=discover(raw)
    if not auctions:raise ValueError('No retained dated catalogues discovered')
    root=corpus.ROOT/'data/historical_source_corpus';root.mkdir(parents=True,exist_ok=True)
    snapshot=corpus.DATA/'sources/barnard-marcus'/('sitemap-'+corpus.digest(raw.encode())[:16]+'.json.gz')
    corpus.save_gzip(snapshot,{'source_url':index,'retrieved_at':corpus.now(),'xml':raw})
    attempted=[];failures=[];captured=0
    for day,url in auctions:
        path=root/('barnard_marcus_'+day.replace('-','_')+'.json')
        prior=json.loads(path.read_text()) if path.exists() else {}
        if prior.get('catalogue_complete') and prior.get('lot_records'):continue
        if len(attempted)>=limit:break
        attempted.append(day)
        print(f'Barnard Marcus: collecting {day} from {url}',flush=True)
        try:
            payload=harvest(url,day,workers=2)
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
        if not(s.get('catalogue_complete') and s.get('lot_records')):remaining.append({'date':day,'url':url})
    result={'checked_at':corpus.now(),'catalogues_discovered':len(auctions),'catalogues_attempted':attempted,
            'lot_rows_captured_this_run':captured,'remaining_catalogues':remaining,'failures':failures,
            'complete':not remaining and not failures,'completion_scope':'Retained official sitemap catalogues only; not a claim of twenty-year completeness'}
    corpus.save_json(corpus.DATA/'barnard_marcus_collection.json',result)
    print(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=4)
    s=run(p.parse_args().limit)
    if s['failures']:raise SystemExit(1)
