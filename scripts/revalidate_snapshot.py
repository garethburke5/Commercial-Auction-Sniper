"""Apply current publication rules to existing facts without claiming a new scan."""
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from collectors.auction_estates import _classified_property_type, _commercial_mixed_evidence
from collectors.symonds_sampson import _property_type
from collectors.core import Lot
from collectors.pattinson import repair_particulars as repair_pattinson
from dataclasses import fields
from run_collectors_resilient import _finalize_published_snapshot
from scripts.repair_legacy_ahl_particulars import repair as repair_ahl
from collectors.publication_quality import commercial_decision, lot_identity, canonical_url


def restore_reclassified_current_lots(data, now=None):
    """Reconsider fresh inspected facts after a classification repair, never stale stock."""
    now=now or datetime.now(timezone.utc)
    try:
        observed=datetime.fromisoformat(data.get('generated_at','').replace('Z','+00:00'))
        age=(now-observed).total_seconds()
    except (TypeError, ValueError):
        return 0
    if not 0 <= age <= 14*3600:
        return 0
    inspected=set()
    for source in data.get('source_health',[]):
        evidence=source.get('reconciliation') or {}
        for row in evidence.get('commercial_lot_evidence') or evidence.get('lot_outcomes') or []:
            if row.get('commercial') is True:
                inspected.add((source['source'],canonical_url(row.get('url')),row.get('auction_date')))
    existing={lot_identity(row) for row in data.get('properties',[])}
    retained=[]; restored=0
    for row in data.get('excluded_properties',[]):
        day=row.get('auction_date')
        key=(row.get('source'),canonical_url(row.get('url')),day)
        if (str(row.get('publication_exclusion','')).startswith('Pure residential:')
            and key in inspected and (not day or day>=now.date().isoformat())
            and str(row.get('status','')).upper()!='ARCHIVED'
            and commercial_decision(row) is True):
            if lot_identity(row) not in existing:
                item=dict(row);item.pop('publication_exclusion',None)
                data.setdefault('properties',[]).append(item)
                existing.add(lot_identity(item));restored+=1
        else:
            retained.append(row)
    data['excluded_properties']=retained
    return restored


def revalidate(path=Path('data/properties.json')):
    data=json.loads(path.read_text())
    repair_ahl(data)
    restored=restore_reclassified_current_lots(data)
    for item in data.get('properties', []):
        if item.get('source') == 'Auction Estates' and item.get('property_type') == 'Mixed Use':
            text=item.get('description') or ''
            if not _commercial_mixed_evidence(text):
                item['property_type']=_classified_property_type('Commercial',text)
        elif item.get('source') == 'Symonds & Sampson':
            item['property_type']=_property_type(item.get('description') or '')
            if not re.fullmatch(r'Lot \d+[A-Z]?', item.get('lot_number') or '', re.I):
                item['lot_number']=None
        elif item.get('source') == 'Pattinson Auction':
            lot = Lot(**{f.name:item[f.name] for f in fields(Lot) if f.name in item})
            item.update(repair_pattinson(lot).to_dict())
    path.write_text(json.dumps(data,indent=2))
    _finalize_published_snapshot(path)
    data=json.loads(path.read_text())
    from source_reconciliation import attach
    attach(data)
    integrity=data.setdefault('integrity',{})
    integrity['publication_revision']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    integrity['revalidated_at']=datetime.now(timezone.utc).isoformat()
    # generated_at and collected_at retain the timestamps of the actual crawl.
    path.write_text(json.dumps(data,indent=2))
    print('REVALIDATED',len(data['properties']),'published rows;',restored,'fresh reclassified lots; collector snapshot',data.get('generated_at'))


if __name__ == '__main__':
    revalidate()
