"""Real templates with public fixture data; no accounts or outside requests."""
import json, sys, tempfile
from pathlib import Path
from web_platform.catalogue import Catalogue
from web_platform.site import Site
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);(root/'data/auction_history').mkdir(parents=True)
    (root/'data/properties.json').write_text(json.dumps({'generated_at':'2026-10-21T08:00:00Z','properties':[{
        'source':'Example Auctions','url':'https://example.com/lot/1','address':'5 High Street, London, AB1 2CD',
        'auction_date':'2099-11-01','lot_number':'1','guide_price':190000,'annual_rent':20000,
        'tenure':'Freehold','property_type':'Retail','description':'A freehold shop investment in the town centre. '*12,
        'image_url':'https://images.example.com/shop.jpg'}]}))
    (root/'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':0,'by_sector':{'commercial':0,'mixed-use':0}}))
    site=Site(Catalogue(root),'https://preview.example');row=site.catalogue.properties[0]
    mode=sys.argv[1] if len(sys.argv)>1 else 'property'
    if mode=='snapshot': html=site.snapshot_page(row)
    elif mode=='cards': html=site.page('/properties/','Properties','list','Find auction properties.',rows=[row])
    else: html=site.page(row['path'],row['address'],'property','Retail investment.',row=row,
                         history_preview={'previous_appearances':2},gallery=[],particulars={},fee={})
    print(html)
