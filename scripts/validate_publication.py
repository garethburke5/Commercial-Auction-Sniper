"""The production publication gate, shared by full scans and snapshot repairs."""
import json, re
from collections import defaultdict, Counter
from pathlib import Path
from source_manifest import manifest_coverage
from collectors.publication_quality import validate_publication
p=Path('data/properties.json')
assert p.exists(), 'data/properties.json was not generated'
d=json.loads(p.read_text(encoding='utf-8'))
validate_publication(d)
assert 'properties' in d and 'archive' in d and 'source_health' in d and d.get('generated_at'), 'invalid snapshot contract'
print('SNAPSHOT',len(d['properties']),'published properties',len(d['archive']),'historical')
for s in d['source_health']:
    print(s['source'],s['status'],s['lots_seen'],'/',s.get('expected_count'))
# publication_resilience intentionally converts temporary FAILED sources with retained
# last-known-good inventory to DEGRADED. Validate the post-resilience state, not the
# collector's pre-resilience failure list.
failed=[s for s in d['source_health'] if str(s.get('status') or '').upper()=='FAILED']
assert not failed, 'unpreserved FAILED collectors: '+', '.join(s['source'] for s in failed)
mismatch=[s for s in d['source_health'] if s.get('expected_count') and s.get('lots_seen')!=s.get('expected_count')]
assert not mismatch, 'catalogue count mismatches: '+', '.join(f"{s['source']} {s['lots_seen']}/{s['expected_count']}" for s in mismatch)
coverage=manifest_coverage(d['source_health'])
print('TARGET COVERAGE',coverage)
assert not coverage['missing_required_sources'], 'required sources absent from source health: '+', '.join(coverage['missing_required_sources'])
assert not coverage['unhealthy_required_sources'], 'required sources unhealthy/unimplemented: '+', '.join(coverage['unhealthy_required_sources'])
assert not coverage['missing_expansion_sources'], 'target expansion sources absent from source health: '+', '.join(coverage['missing_expansion_sources'])
assert not coverage['unhealthy_expansion_sources'], 'target expansion sources unhealthy/unimplemented: '+', '.join(coverage['unhealthy_expansion_sources'])
assert coverage['acceptance_ready'], 'configured source universe is not acceptance-ready'
integrity=d.get('integrity') or {}
assert integrity.get('target_coverage') is not None, 'target coverage missing from production snapshot'
assert integrity.get('acceptance_ready') is True, 'snapshot integrity does not certify target acceptance'
assert not integrity.get('quality_rejections'), f"quality gate rejected {integrity.get('quality_rejections')} records: {integrity.get('quality_rejection_reasons')}"
quality=integrity.get('source_quality') or {}
published_counts=Counter(str(x.get('source') or '') for x in d['properties'])
health={s['source']:s for s in d['source_health']}
hard_quality_sources={src for src,count in published_counts.items() if count >= 3 and health.get(src,{}).get('status') in {'LIVE','DEGRADED'} and health.get(src,{}).get('authoritative_snapshot') is True}
advisory_sources={src for src,count in published_counts.items() if count >= 3 and health.get(src,{}).get('status') in {'LIVE','DEGRADED'} and src not in hard_quality_sources}
image_fail=[];rich_fail=[];missing_quality=[]
for src in sorted(hard_quality_sources):
    q=quality.get(src)
    if not q or not q.get('lots'):
        source_rows=[x for x in d['properties'] if str(x.get('source') or '')==src]
        terminal_statuses={'SOLD PRIOR','WITHDRAWN','WITHDRAWN PRIOR','POSTPONED','AUCTION ENDED','COMPLETED','ARCHIVED'}
        nonterminal=[x for x in source_rows if str(x.get('status') or '').strip().upper().replace('_',' ') not in terminal_statuses]
        if nonterminal: missing_quality.append(src)
        continue
    if q.get('image_coverage_pct',0)<80:image_fail.append(f"{src} {q.get('image_coverage_pct',0)}%")
    if q.get('rich_coverage_pct',0)<60:rich_fail.append(f"{src} {q.get('rich_coverage_pct',0)}%")
assert not missing_quality, 'authoritative live sources missing active-row quality telemetry: '+', '.join(missing_quality)
assert not image_fail, 'authoritative live-source genuine image coverage below 80%: '+', '.join(image_fail)
assert not rich_fail, 'authoritative live-source rich-particular coverage below 60%: '+', '.join(rich_fail)
for src in sorted(advisory_sources):
    q=quality.get(src) or {}
    if q.get('image_coverage_pct',100)<80 or q.get('rich_coverage_pct',100)<60: print('QUALITY ADVISORY',src,q)
bad_vacant=[x for x in d['properties'] if str(x.get('occupation') or '').strip().lower() in {'vacant','vacant possession'} and (x.get('annual_rent') is not None or x.get('gross_yield') is not None)]
assert not bad_vacant, f'vacant rent/yield integrity failures: {len(bad_vacant)}'
boiler=re.compile(r'login|log in|register to bid|cancel proxy bid|your bid|wishlist|connecting to auction|please wait',re.I)
bad_titles=[x for x in d['properties'] if boiler.search(str(x.get('address') or ''))]
assert not bad_titles, f'boilerplate property titles: {len(bad_titles)}'
bad_descriptions=[x for x in d['properties'] if boiler.search(str(x.get('description') or ''))]
assert not bad_descriptions, f'boilerplate property descriptions: {len(bad_descriptions)}'
identities=defaultdict(set)
for x in d['properties']:
    lot=str(x.get('lot_number') or '').strip().upper(); address=re.sub(r'\s+',' ',str(x.get('address') or '').strip().lower()); day=str(x.get('auction_date') or '')[:10]; url=str(x.get('url') or '').strip()
    if lot and lot not in {'LOT TBC','TBC'} and address and day and url: identities[(str(x.get('source') or ''),day,lot,address)].add(url)
duplicate_identities={k:v for k,v in identities.items() if len(v)>1}
assert not duplicate_identities, 'duplicate lot identities across detail URLs: '+repr({k:sorted(v) for k,v in list(duplicate_identities.items())[:10]})
sav=[x for x in d['properties'] if x.get('source')=='Savills Auctions']
assert sav, 'no current Savills lots published'
