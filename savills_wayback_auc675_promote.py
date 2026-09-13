from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from history_database import update_history_database

SOURCE = 'Savills Auctions'
AUCTION_DATE = '2010-05-10'
HISTORY = Path('data/property_history.json')
PROGRESS = Path('data/historical_backfill_progress.json')
EVIDENCE = Path('data/source_diagnostics/savills_wayback_commercial_lot_recovery.json')
DIAG = Path('data/source_diagnostics/savills_wayback_auc675_promotion.json')

MONEY = r'£\s*([0-9][0-9,]*)'
GUIDE_RE = re.compile(r'Guide\s*Price\s*' + MONEY + r'(?:\s*[-–]\s*£?\s*([0-9][0-9,]*))?', re.I)
RESULT_RE = re.compile(r'\bResult\s*' + MONEY, re.I)
RENT_RE = re.compile(r'(?:Current\s+Rent\s+Reserved|Rent\s+Reserved|Current\s+Rent)\s*:?\s*' + MONEY + r'\s*(?:p\.?a\.?|pa|per\s+annum)?', re.I)
TENURE_RE = re.compile(r'\bTenure\s+(Freehold|Leasehold)\b', re.I)
TENANT_RE = re.compile(r'\bLet\s+to\s+(.+?)\s+until\s+(\d{4})\b', re.I)
POSTCODE_RE = re.compile(r'\b(?:GIR ?0AA|[A-Z]{1,2}\d[A-Z\d]? ?\d[A-Z]{2})\b', re.I)
COMMERCIAL_RE = re.compile(r'\b(retail|shop|bank|office|industrial|warehouse|restaurant|public house|pub|supermarket|medical|pharmacy|garage|workshop|commercial|investment|mixed[- ]use)\b', re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def money(m):
    return int(m.replace(',', '')) if m else None


def property_address(page):
    for h in page.get('headings') or []:
        if POSTCODE_RE.search(h) and not re.search(r"Solicitor|Seller|E-mail|Tel|Fax", h, re.I):
            return re.sub(r'\s+', ' ', h).strip(' •')
    text = page.get('text') or ''
    # Conservative fallback: only the address phrase immediately following Map.
    m = re.search(r'\bMap\s+\S+\s+(.{8,220}?' + POSTCODE_RE.pattern + r')(?:\s+[•]|\s+Freehold|\s+Leasehold)', text, re.I)
    return re.sub(r'\s+', ' ', m.group(1)).strip(' •') if m else None


def property_type(page, text):
    for h in page.get('headings') or []:
        if COMMERCIAL_RE.search(h) and ('•' in h or re.search(r'\b(?:Freehold|Leasehold)\b', h, re.I)):
            return re.sub(r'^\s*[•·-]+\s*', '', re.sub(r'\s+', ' ', h)).strip()
    m = re.search(r'[•·]\s*((?:Freehold|Leasehold)\s+[^•]{1,100}?(?:Investment|Retail|Shop|Bank|Office|Industrial|Warehouse|Restaurant|Commercial|Mixed[- ]Use))\b', text, re.I)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else None


def parse_page(page):
    if page.get('replay_status') != 200:
        return None, 'not-http-200'
    lot = str(page.get('lot_number') or '').strip()
    text = re.sub(r'\s+', ' ', page.get('text') or '')
    address = property_address(page)
    guide = GUIDE_RE.search(text)
    result = RESULT_RE.search(text)
    ptype = property_type(page, text)
    if not lot:
        return None, 'missing-lot-number'
    if not address or not POSTCODE_RE.search(address):
        return None, 'missing-full-address'
    if not result:
        return None, 'missing-explicit-result'
    if not ptype or not COMMERCIAL_RE.search(ptype):
        return None, 'not-explicitly-commercial-or-mixed'

    rent_m = RENT_RE.search(text)
    tenure_m = TENURE_RE.search(text)
    tenant_m = TENANT_RE.search(text)
    sale_price = money(result.group(1))
    annual_rent = money(rent_m.group(1)) if rent_m else None
    gross_yield = round(annual_rent / sale_price * 100, 2) if annual_rent and sale_price else None
    guide_low = money(guide.group(1)) if guide else None
    guide_high = money(guide.group(2)) if guide and guide.lastindex and guide.lastindex >= 2 else None
    source_url = page.get('target_url') or (page.get('capture') or [None, None])[1]
    replay_url = page.get('replay_url')

    desc_parts = []
    if guide_high and guide_high != guide_low:
        desc_parts.append(f'Published guide range £{guide_low:,}-£{guide_high:,}.')
    desc_parts.append('Recovered from a first-party Savills Auctions lot page archived by the Internet Archive.')
    if replay_url:
        desc_parts.append(f'Archived replay: {replay_url}')

    row = {
        'source': SOURCE,
        'url': source_url,
        'source_id': f'legacy-auc675-pos{page.get("pos")}',
        'auction_date': AUCTION_DATE,
        'lot_number': lot,
        'address': address,
        'status': 'SOLD',
        'guide_price': guide_low,
        'sale_price': sale_price,
        'annual_rent': annual_rent,
        'gross_yield': gross_yield,
        'tenure': tenure_m.group(1).title() if tenure_m else None,
        'property_type': ptype,
        'tenant': re.sub(r'\s+', ' ', tenant_m.group(1)).strip(' .') if tenant_m else None,
        'lease_term': f'until {tenant_m.group(2)}' if tenant_m else None,
        'lease_expiry': tenant_m.group(2) if tenant_m else None,
        'occupation': 'LET' if tenant_m else None,
        'description': ' '.join(desc_parts),
    }
    return row, None


def main():
    evidence = json.loads(EVIDENCE.read_text(encoding='utf-8'))
    if evidence.get('auction_date') != AUCTION_DATE:
        raise RuntimeError(f'Unexpected evidence auction date: {evidence.get("auction_date")}')
    pages = evidence.get('page_results') or []
    rows, rejected = [], []
    seen = set()
    for page in pages:
        row, reason = parse_page(page)
        if reason:
            rejected.append({'pos': page.get('pos'), 'lot_number': page.get('lot_number'), 'reason': reason})
            continue
        key = (row['auction_date'], row['lot_number'], row['address'].lower())
        if key in seen:
            rejected.append({'pos': page.get('pos'), 'lot_number': page.get('lot_number'), 'reason': 'duplicate-within-evidence'})
            continue
        seen.add(key)
        rows.append(row)

    before_db = json.loads(HISTORY.read_text(encoding='utf-8'))
    before = sum(1 for e in before_db.get('auction_events', []) if e.get('source') == SOURCE)
    db = update_history_database(rows, path=HISTORY)
    after = sum(1 for e in db.get('auction_events', []) if e.get('source') == SOURCE)
    added = after - before

    progress = json.loads(PROGRESS.read_text(encoding='utf-8'))
    state = progress.setdefault('sources', {}).setdefault(SOURCE, {})
    at = now_iso()
    state['last_history_event_count'] = after
    state['lots_captured'] = after
    if added > 0:
        prior = state.get('earliest_date_reached')
        state['earliest_date_reached'] = min(prior, AUCTION_DATE) if prior else AUCTION_DATE
        prior_month = state.get('earliest_month_reached')
        state['earliest_month_reached'] = min(prior_month, '2010-05') if prior_month else '2010-05'
        state['last_success'] = at
    state['last_discovery_mode'] = 'savills-wayback-direct-first-party-lot-promotion-auc675'
    state['historically_complete'] = False
    state['discovery_exhausted'] = False
    state['status'] = 'LIVE ARCHIVE INGESTING' if added else 'LIVE ARCHIVE BLOCKED'
    state['savills_wayback_auc675_promotion_last_run'] = {
        'at': at,
        'auction_date': AUCTION_DATE,
        'pages_considered': len(pages),
        'validated_rows': len(rows),
        'rejected_rows': rejected,
        'canonical_events_before': before,
        'canonical_events_after': after,
        'canonical_events_added': added,
    }
    state['propertyauctions_cursor_last_blocker'] = {
        'at': at,
        'route': 'savills-wayback-direct-first-party-lot-promotion-auc675',
        'failing_url_or_route': 'older first-party Savills commercial Auc IDs discovered in the archival manifest',
        'message': f'Auc=675 direct first-party lot pages yielded {len(rows)} validated commercial/mixed-use rows and {added} newly persisted canonical events. The next-oldest source-specific task is to enumerate and replay older commercial Auc IDs rather than stopping at 2010.',
        'next_safe_route': 'Use the persisted Wayback first-party namespace manifest to enumerate every older comm_previous_auction_detail.asp / comm_previous_auction_lot.asp Auc ID and recover its lot positions with the alternate HTTP replay method that succeeded for Auc=675; promote only explicit commercial/mixed-use pages with full address and lot-level facts.',
    }
    progress['updated_at'] = at
    PROGRESS.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8')
    DIAG.parent.mkdir(parents=True, exist_ok=True)
    DIAG.write_text(json.dumps({
        'at': at,
        'route': state['last_discovery_mode'],
        'auction_date': AUCTION_DATE,
        'validated_rows': rows,
        'rejected_rows': rejected,
        'canonical_events_before': before,
        'canonical_events_after': after,
        'canonical_events_added': added,
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({
        'auction_date': AUCTION_DATE,
        'pages_considered': len(pages),
        'validated_rows': len(rows),
        'rejected_rows': len(rejected),
        'canonical_events_before': before,
        'canonical_events_after': after,
        'canonical_events_added': added,
        'earliest_verified': state.get('earliest_date_reached'),
    }, indent=2))


if __name__ == '__main__':
    main()
