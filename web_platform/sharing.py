"""Public-only sharing copy, reused by pages, cards and snapshots."""
import re
from urllib.parse import urlsplit


def share_details(row, origin):
    title = str(row.get('address') or 'Auction property')
    kind = str(row.get('property_type') or 'Property').strip()
    source = str(row.get('source') or 'the auctioneer')
    parts = [f"{kind} at auction with {source}."]
    if row.get('guide') and row['guide'] != 'Not stated':
        parts.append(f"Guide price {row['guide']}.")
    if row.get('auction_date'):
        from .site import uk_date
        parts.append(f"Auction {uk_date(row['auction_date'])}.")
    if row.get('unavailable'):
        parts.append(f"Status: {row['unavailable']}.")
    # Use public structured facts only; never premium history, notes or pack text.
    description = re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    image = str(row.get('image_url') or '')
    if urlsplit(image).scheme not in ('http', 'https'):
        image = ''
    return {'title': title + ' | Auction Geek', 'text': description,
            'url': origin.rstrip('/') + row['path'], 'image': image,
            'image_alt': title + ' — property photograph'}
