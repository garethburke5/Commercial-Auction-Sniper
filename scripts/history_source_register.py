"""Keep directory discovery, retained evidence and collection failures distinct."""
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
from urllib.request import Request,urlopen
from urllib.parse import urljoin,urlparse
import json,re,sys
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1]
DIRECTORY='https://www.eigpropertyauctions.co.uk/auctioneer'


def discover(html):
    found={}
    for a in BeautifulSoup(html,'html.parser').select('a[href]'):
        u=urljoin(DIRECTORY,a['href']);p=urlparse(u)
        if p.hostname!='www.eigpropertyauctions.co.uk' or not re.fullmatch(r'/auctioneer/[^/]+',p.path):continue
        name=a.get_text(' ',strip=True)
        if name:found[u]={'name':name,'directory_url':u,'scope_status':'requires UK/branch/trading-name reconciliation'}
    if not found:raise ValueError('Directory exposed no auctioneer entries; previous inventory must be retained')
    return sorted(found.values(),key=lambda x:x['name'].casefold())


def build(progress,directory,registry,continuation,catalogues):
    # Exact names and explicitly evidenced shared feeds only. Never fuzzy-merge
    # competing houses or count a branch name as a separate proven operator.
    aliases={}
    for entry in registry.get('sources',[]):
        if entry.get('relationship_evidence') and entry.get('brand') and entry.get('source'):
            aliases[entry['brand']]=entry['source']
    holdings=progress.get('by_auctioneer',{})
    years=progress.get('twenty_year_coverage',{}).get('by_auctioneer_and_year',[])
    entries=[]
    for entry in directory:
        name=entry['name'];label=name if name in holdings else aliases.get(name,name)
        annual=[r for r in years if r['auctioneer']==label]
        entries.append({**entry,'matched_corpus_label':label if label in holdings else None,
            'match_basis':'exact label' if label==name and label in holdings else 'existing evidenced source registry' if label in holdings else None,
            'retained_appearances':holdings.get(label,0),'years_with_retained_evidence':[r['year'] for r in annual],
            'with_guide_price':sum(r['with_guide_price'] for r in annual),'with_sale_price':sum(r['with_sale_price'] for r in annual),
            'collection_status':'partial holdings; full coverage unverified' if label in holdings else 'not linked to retained corpus; source assessment required',
            'twenty_year_complete':False})
    latest={}
    for run in continuation.get('runs',[]):latest[run['source']]=run
    latest.update(continuation.get('latest_by_source',{}))
    gaps=[]
    for path,s in catalogues:
        if not s.get('catalogue_complete') or s.get('errors'):
            gaps.append({'state_file':path,'auctioneer':s.get('auctioneer'),'auction_date':s.get('auction_date'),
                         'source_url':s.get('source_url'),'lots_captured':s.get('lots_captured'),
                         'errors':s.get('errors',[]),'checked_at':s.get('checked_at')})
    return {'generated_at':datetime.now(timezone.utc).isoformat(),'corpus_checkpoint':progress.get('generated_at'),
        'scope':'All sectors; preceding twenty years; retain older evidence. Directory entries are candidates, not a verified national denominator.',
        'national_completeness_verified':False,'directory_entries':entries,
        'directory_entry_count':len(entries),'directory_entries_not_linked':sum(not x['matched_corpus_label'] for x in entries),
        'corpus_labels':holdings,'price_coverage':progress.get('twenty_year_coverage',{}),
        'latest_collector_attempts':latest,'unresolved_catalogues':gaps,
        'limits':['Zero exact-name matches does not prove no records exist under another trading name.',
                  'Completed collection attempts do not prove complete archives or populated prices.',
                  'Directory membership alone does not establish current activity, UK geography or distinct operator status.']}


def run(root=ROOT):
    root=Path(root);folder=root/'data/auction_history';path=folder/'source_register.json'
    previous=json.loads(path.read_text()) if path.exists() else {}
    discovery=previous.get('directory_discovery',{})
    directory=previous.get('directory_entries',[])
    try:
        with urlopen(Request(DIRECTORY,headers={'User-Agent':'AuctionGeek historical coverage research'}),timeout=30) as response:raw=response.read()
        directory=discover(raw.decode('utf-8','replace'))
        discovery={'source_url':DIRECTORY,'checked_at':datetime.now(timezone.utc).isoformat(),'sha256':sha256(raw).hexdigest(),'status':'retrieved'}
    except Exception as exc:
        discovery={**discovery,'last_attempt_at':datetime.now(timezone.utc).isoformat(),'status':'refresh failed; previous inventory retained','error':str(exc)[:400]}
    read=lambda p:json.loads(p.read_text()) if p.exists() else {}
    catalogues=[]
    for p in (folder/'auctions').rglob('*.json'):
        try:catalogues.append((str(p.relative_to(root)),read(p)))
        except (OSError,ValueError):catalogues.append((str(p.relative_to(root)),{'errors':['unreadable state']}))
    result=build(read(folder/'progress.json'),directory,read(root/'config/source_registry.json'),read(folder/'continuation_collection.json'),catalogues)
    result['directory_discovery']=discovery
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['generated_at','directory_entry_count','directory_entries_not_linked','national_completeness_verified']}))
    return result

if __name__=='__main__':run()
