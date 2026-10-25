"""Real property templates and search bundles for mobile layout acceptance."""
import json
import tempfile
from pathlib import Path
from web_platform.catalogue import Catalogue
from web_platform.site import Site

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    (root / 'data/auction_history').mkdir(parents=True)
    properties = [{
        'source': 'Example Auctions', 'url': f'https://example.com/lot/{n}',
        'address': f'{n} High Street, Longtown, West Yorkshire, AB1 2CD',
        'auction_date': '2099-11-01', 'lot_number': str(n), 'guide_price': 190000,
        'annual_rent': 20000, 'tenure': 'Freehold', 'property_type': 'Retail',
        'description': 'A freehold shop investment in the town centre.',
        'image_url': 'https://images.example.com/shop.jpg',
    } for n in range(1, 13)]
    (root / 'data/properties.json').write_text(json.dumps({'generated_at': '2026-10-25T08:00:00Z', 'properties': properties}))
    (root / 'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured': 0, 'by_sector': {'commercial': 0, 'mixed-use': 0}}))
    site = Site(Catalogue(root), 'https://preview.example')
    rows = site.catalogue.properties
    rows[0]['guide'] = '£190,000–£200,000'
    html = site.page('/properties/', 'Auction properties', 'list', 'Find auction properties.', rows=rows, board=True, page=1, pages=1)
    catalogue = site.page('/auction-catalogue/', 'Auction catalogue', 'catalogue', 'Properties in this auction.', rows=rows)
    print(json.dumps({'html': html, 'catalogue': catalogue, 'assets': dict(site.board_assets())}))
