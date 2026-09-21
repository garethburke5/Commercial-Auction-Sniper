"""Apply current publication rules to existing facts without claiming a new scan."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from collectors.auction_estates import _classified_property_type, _commercial_mixed_evidence
from collectors.symonds_sampson import _property_type
from run_collectors_resilient import _finalize_published_snapshot


def revalidate(path=Path('data/properties.json')):
    data=json.loads(path.read_text())
    for item in data.get('properties', []):
        if item.get('source') == 'Auction Estates' and item.get('property_type') == 'Mixed Use':
            text=item.get('description') or ''
            if not _commercial_mixed_evidence(text):
                item['property_type']=_classified_property_type('Commercial',text)
        elif item.get('source') == 'Symonds & Sampson':
            item['property_type']=_property_type(item.get('description') or '')
    path.write_text(json.dumps(data,indent=2))
    _finalize_published_snapshot(path)
    data=json.loads(path.read_text())
    integrity=data.setdefault('integrity',{})
    integrity['publication_revision']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    integrity['revalidated_at']=datetime.now(timezone.utc).isoformat()
    # generated_at and collected_at retain the timestamps of the actual crawl.
    path.write_text(json.dumps(data,indent=2))
    print('REVALIDATED',len(data['properties']),'published rows; collector snapshot',data.get('generated_at'))


if __name__ == '__main__':
    revalidate()
