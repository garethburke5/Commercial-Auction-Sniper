import json
from datetime import date

from collectors.core import Lot, SourceResult


def lot(number, status='CURRENT', day='2099-10-01'):
    return Lot('Example auctioneer', f'https://example.test/lot/{number}',
               f'{number} High Street, AB1 2CD', lot_number=str(number),
               auction_date=day, status=status, property_type='Retail',
               tenure='Freehold', guide_price=100000, annual_rent=10000,
               description='Freehold retail shop investment with commercial lease. '*5)


def test_full_collection_retains_withdrawn_lot_removed_by_auctioneer(tmp_path, monkeypatch):
    import run_collectors as pipeline
    from run_collectors_resilient import _finalize_published_snapshot
    withdrawn=lot(2,'WITHDRAWN','2020-01-01').to_dict()
    (tmp_path/'properties.json').write_text(json.dumps({'properties':[], 'archive':[withdrawn]}))
    result=SourceResult('Example auctioneer','LIVE',[lot(1)],expected_count=1,
                        authoritative_snapshot=True,scope_dates=('2099-10-01','2020-01-01'))
    monkeypatch.setattr(pipeline,'DATA',tmp_path)
    monkeypatch.setattr(pipeline,'COLLECTORS',[lambda:result])
    pipeline.run()
    _finalize_published_snapshot(tmp_path/'properties.json',today=date(2026,10,17))
    snapshot=json.loads((tmp_path/'properties.json').read_text())
    assert any(r['url']==withdrawn['url'] and r['status']=='WITHDRAWN' for r in snapshot['archive'])
    assert all(r['url']!=withdrawn['url'] for r in snapshot['properties'])
