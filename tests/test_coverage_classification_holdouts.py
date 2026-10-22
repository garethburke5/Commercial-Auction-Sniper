import json
from pathlib import Path
from datetime import datetime,timezone
import pytest
from collectors.publication_quality import commercial_decision
from collectors.core import clean_description
from scripts.revalidate_snapshot import restore_reclassified_current_lots

CASES=json.loads((Path(__file__).parent/'fixtures/commercial_coverage_holdouts.json').read_text())

@pytest.mark.parametrize('row',CASES,ids=[r['address'] for r in CASES])
def test_existing_commercial_accommodation_survives_residential_proposals(row):
    assert commercial_decision(row) is True
    cleaned=clean_description(row['description'])
    assert 'Skip navigation' not in cleaned
    assert 'The map and satellite images' not in cleaned

@pytest.mark.parametrize('description',[
 'A three-bedroom family house with office space. Close to an outdoor leisure centre.',
 'A two bedroom flat. Local amenities include an equestrian facility.',
 'A leasehold flat located in a mixed-use building with a ground floor shop.',
 'A former public house conversion now offered as a two-bedroom home.',
 'A former hotel demolished for residential development of 12 apartments.',
])
def test_commercial_keywords_do_not_convert_residential_assets(description):
    assert commercial_decision({'description':description,'property_type':'Residential'}) is False


def test_reclassification_only_restores_fresh_inspected_current_assets():
    now=datetime(2026,10,22,14,tzinfo=timezone.utc)
    row=dict(CASES[0],auction_date='2026-11-03')
    data={'generated_at':now.isoformat(),'properties':[], 'excluded_properties':[row],
          'source_health':[{'source':row['source'],'reconciliation':{'commercial_lot_evidence':[
              {'url':row['url'],'auction_date':row['auction_date'],'commercial':True}]}}]}
    assert restore_reclassified_current_lots(data,now)==1
    assert restore_reclassified_current_lots(data,now)==0
    assert len(data['properties'])==1 and not data['excluded_properties']
    for changed in ({'generated_at':'2026-10-21T00:00:00+00:00'}, {'source_health':[]}):
        fresh={**data, 'properties':[], 'excluded_properties':[row], **changed}
        assert restore_reclassified_current_lots(fresh,now)==0
        assert not fresh['properties']
