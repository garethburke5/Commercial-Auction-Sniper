"""Read-only catalogue-wide relationship check against the retained auction archive.

Uses the production classifier. Counts are candidates classified from recorded
addresses/interest/area, not independently verified Land Registry title links.
"""
import argparse,json,sqlite3
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone,date
from types import SimpleNamespace
from web_platform.catalogue import Catalogue
from web_platform.market_context import MarketContext,same_property_address
from web_platform.property_relationships import candidate_keys,relationship

def check(root,history_path=None):
    c=Catalogue(root,summaries=False)
    if history_path:c.history_path=Path(history_path)
    m=MarketContext(c);m.load()
    output=[];types=Counter();checks=0
    for row in c.properties:
        if not row.get('auction_date'):continue
        refs=[]
        for anchor in candidate_keys(row):refs.extend(m.by_relationship.get(anchor,[]))
        found=[];seen=set()
        for old in m._records(refs):
            checks+=1
            if m._url_key(old)==m._url_key(row) and old.get('auction_date')==row.get('auction_date'):continue
            if old.get('auction_date','')>=row.get('auction_date',''):continue
            pair=relationship(old,row,same_address=same_property_address(old['address'],row['address']))
            if not pair or pair['match_type']!='related_interest':continue
            key=(m._url_key(old),old.get('auction_date'),old['address'])
            if key in seen:continue
            seen.add(key)
            for reason in pair['relationship_reasons']:types[reason.split(':')[0] if ':' in reason else reason]+=1
            found.append({'address':old['address'],'auctioneer':old.get('auctioneer'),'auction_date':old.get('auction_date'),
                          'tenure':old.get('tenure'),'source_url':old.get('original_url'),'reasons':pair['relationship_reasons']})
        if found:output.append({'address':row['address'],'property_path':row['path'],'tenure':row.get('tenure'),'auction_date':row.get('auction_date'),'related':found})
    return {'checked_at':datetime.now(timezone.utc).isoformat(),'catalogue_generated_at':c.generated_at,
            'catalogue_listings_checked':len(c.properties),'candidate_pairs_checked':checks,
            'listings_with_related_offerings':len(output),'related_offerings':sum(len(r['related']) for r in output),
            'reason_counts':dict(types),'limitations':'Address/title candidates with recorded differences; not proof of legal title genealogy. No records merged or deleted.',
            'listings':output}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--history-path');p.add_argument('--output',required=True);a=p.parse_args()
    result=check(a.root,a.history_path);Path(a.output).write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='listings'},indent=2))
