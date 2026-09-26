"""Refresh records affected by the former whole-page AHL parser, once per row."""
from concurrent.futures import ThreadPoolExecutor, as_completed

from collectors.auction_house_london_detail import parse_lot
from collectors.utils import soup


def repair(data):
    targets={}
    for group in ('properties','archive'):
        for row in data.get(group,[]):
            if row.get('source')=='Auction House London' and 'Financial Tools' in str(row.get('description','')):
                url=row.get('url','')
                if url.startswith('https://auctionhouselondon.co.uk/lot/'):
                    targets.setdefault(url,[]).append(row)
    repaired=0
    def fetch(url,rows):
        lot=parse_lot(soup(url,use_browser=False),url,rows[0].get('lot_number'),rows[0].get('auction_date'))
        if not lot: raise ValueError('Own lot particulars unavailable')
        return lot.to_dict()
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(fetch,url,rows):url for url,rows in targets.items()}
        for job in as_completed(jobs):
            url=jobs[job]
            try:
                fresh=job.result()
                for row in targets[url]:
                    # Never overwrite an earlier auction with a later relisting.
                    old_day=str(row.get('auction_date') or '')[:10]
                    new_day=str(fresh.get('auction_date') or '')[:10]
                    if old_day and new_day and old_day!=new_day:
                        continue
                    row.update(fresh)
                    repaired+=1
            except Exception as exc:
                print('AHL_PARTICULARS_REPAIR_FAILED',url,str(exc),flush=True)
    print('AHL_PARTICULARS_REPAIRED',repaired,'rows from',len(targets),'source pages',flush=True)
    return repaired
