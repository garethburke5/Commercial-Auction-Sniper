"""Reuse the existing market corpus without relabelling it as fresh research."""


def corpus_records(context):
    records=[]
    for group,kind in (('history','marketing_history'),('comparables','sale_comparable')):
        for i,row in enumerate((context or {}).get(group,[])):
            url=row.get('url') or row.get('source_url')
            if not isinstance(url,str) or not url.startswith(('http://','https://')):
                continue
            status=str(row.get('status') or '').lower().replace(' ','_')
            sold=status in ('sold','sold_prior','sold_after','sold_at_auction')
            price=row.get('sale_price') if sold and row.get('sale_price') else row.get('guide_price')
            basis='auctioneer_reported' if sold and row.get('sale_price') else 'guide'
            date=row.get('auction_date') or 'date unrecorded'
            description=f"{date}: {row.get('address','')}. "
            if price is not None:description+=f"£{price:,.0f} {basis.replace('_',' ')}. "
            if row.get('why'):description+='; '.join(row['why'])+'. '
            description+='Banked catalogue evidence; extent, tenancy differences and completion require verification.'
            records.append({'id':f'corpus-{group}-{i}','kind':kind,'subject':row.get('address'),
                'price':price,'price_basis':basis,'comparable':False,'description':description,
                'source':{'title':str(row.get('source') or 'Banked auction')+' / '+str(row.get('address') or '')+' / '+date,'url':url},
                'provenance':'banked_catalogue','comparison_metrics':row.get('comparison_metrics',{})})
    return records
