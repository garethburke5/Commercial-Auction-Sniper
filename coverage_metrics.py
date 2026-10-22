"""Comparable catalogue coverage. Missing evidence is not a zero denominator."""
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from board_presentation import current_board_row
from collectors.publication_quality import publication_exclusion


def url_key(value):
    p = urlsplit(str(value or ''))
    # Keep query parameters: several auctioneers identify lots in the query.
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), p.query, ''))


def source_metrics(snapshot, history, registry, now=None):
    now = now or datetime.now(timezone.utc)
    health = {h['source']: h for h in snapshot.get('source_health', [])}
    inventories = {r['auctioneer']: r for r in registry.get('priority_assessments', [])}
    recon = {r['auctioneer']: r for r in snapshot.get('source_reconciliation', {}).get('sources', [])}
    rows = snapshot.get('properties', []) + snapshot.get('archive', [])
    result = []
    for name in sorted(set(health) | set(inventories)):
        h = health.get(name, {}); t = h.get('reconciliation') or {}; a = inventories.get(name, {})
        storefront_urls=set()
        if not h and a.get('storefront_region'):
            h=health.get(a.get('canonical_source'),{})
            storefront=next((s for s in (h.get('reconciliation') or {}).get('storefronts',[]) if s.get('region')==a['storefront_region']),{})
            storefront_urls=set(storefront.get('lot_urls') or [])
            t={'scope':'Shared regional storefront; published lot links reconciled separately from the canonical feed. Commercial denominator remains unverified.',
               'source_lot_count':storefront.get('source_lot_count'),'catalogue_pages':[storefront['source_url']] if storefront.get('source_url') else [],'discovery_failures':[]}
        names={name,*a.get('brand_names',[])}
        own = [r for r in rows if r.get('source') in names or names.intersection(r.get('source_brands') or []) or (r.get('url') in storefront_urls and current_board_row(r))]
        published = [r for r in own if not publication_exclusion(r)]
        evidence = t.get('commercial_lot_evidence') or t.get('lot_outcomes') or []
        inspected_dates = {url_key(r.get('url')): r.get('auction_date') for r in evidence if r.get('commercial') is True}
        captured = {url_key(r.get('url')) for r in published if r.get('auction_date') == inspected_dates.get(url_key(r.get('url')))}
        expected = t.get('source_commercial_urls')
        comparable = t.get('commercial_inventory_complete') is True and isinstance(expected, list)
        source_urls = {url_key(u) for u in expected} if comparable else set()
        missing = sorted(source_urls - captured) if comparable else None
        captured_count = len(source_urls & captured) if comparable else None
        official_count = len(source_urls) if comparable else None
        duplicates = Counter((url_key(r.get('url')), r.get('auction_date')) for r in own)
        last = h.get('last_successful_collection') or recon.get(name, {}).get('last_successful_collection')
        if not last and h.get('collector_executed') and h.get('status') == 'LIVE': last = h.get('checked_at')
        try:
            stamp = datetime.fromisoformat(last.replace('Z', '+00:00'))
            age = round((now - stamp).total_seconds() / 3600, 1) if stamp.tzinfo else None
        except (AttributeError, ValueError, TypeError): age = None
        errors = list(t.get('discovery_failures') or [])
        if h.get('status') in ('DEGRADED', 'FAILED') and h.get('message') and not errors: errors.append(h['message'])
        outcomes = evidence
        assessed = [r for r in outcomes if r.get('commercial') is True and r.get('auction_date', '9999') < now.date().isoformat()]
        known = sum(r.get('status') in ('SOLD','SOLD PRIOR','SOLD AFTER','UNSOLD','WITHDRAWN','POSTPONED') for r in assessed)
        historical_names = a.get('historical_names') or [name]
        historical = sum((history.get('by_auctioneer') or {}).get(n, 0) for n in historical_names)
        catalogue_urls = t.get('catalogue_pages')
        if not isinstance(catalogue_urls,list):catalogue_urls = [t['catalogue_url']] if t.get('catalogue_url') else a.get('catalogue_urls') or []
        result.append({
            'source': name, 'status': h.get('coverage_status') or h.get('status') or 'NOT INTEGRATED',
            'expected_count': h.get('expected_count'), 'lots_seen': h.get('lots_seen'),
            'published_rows': sum(current_board_row(r) for r in published), 'checked_at': h.get('checked_at'),
            'official_commercial_lots': official_count, 'comparable_captured_lots': captured_count,
            'coverage_pct': round(100 * captured_count / official_count, 1) if official_count else None,
            'coverage_scope': t.get('scope') or 'Catalogue denominator not independently reconciled',
            'missing_lots': missing, 'duplicate_lots': sum(n - 1 for n in duplicates.values() if n > 1),
            'last_successful_collection': last, 'hours_since_success': age, 'stale': age is not None and age > 14,
            'collection_errors': errors, 'historical_records': historical,
            'result_scope_lots': len(assessed), 'reported_outcomes': known,
            'reported_outcome_pct': round(100 * known / len(assessed), 1) if assessed else None,
            'catalogue_urls': [u for u in catalogue_urls if isinstance(u,str)],
            'remaining': a.get('failure_reason'), 'canonical_source': a.get('canonical_source', name),
            'message': h.get('message'), 'reconciliation': {k:(v if isinstance(v,(str,int,float,bool)) or v is None else {'record_count':len(v)}) for k,v in t.items()},
        })
    return result
