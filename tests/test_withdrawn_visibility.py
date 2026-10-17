import json
from datetime import date

from bs4 import BeautifulSoup

from board_presentation import available_row
from collectors.core import Lot, SourceResult
from web_platform.catalogue import Catalogue, identity
from web_platform.site import Site
from web_platform.search_monitoring import matches


def lot(number, status='CURRENT', day='2099-10-01'):
    return Lot('Example auctioneer', f'https://example.test/lot/{number}',
               f'{number} High Street, AB1 2CD', lot_number=str(number),
               auction_date=day, status=status, property_type='Retail',
               tenure='Freehold', guide_price=100000, annual_rent=10000,
               description='Freehold retail shop investment with commercial lease. '*5)


def test_archived_withdrawals_are_searchable_labelled_and_in_total(tmp_path):
    data=tmp_path/'data'
    (data/'auction_history').mkdir(parents=True)
    current=lot(1).to_dict()
    withdrawn=lot(2, 'WITHDRAWN', '2020-01-01').to_dict()
    prior=lot(3, 'WITHDRAWN PRIOR', '2020-02-01').to_dict()
    stale=lot(4, 'STALE SOURCE').to_dict()
    (data/'properties.json').write_text(json.dumps({'properties':[current],
        'archive':[withdrawn, prior, stale], 'generated_at':'2026-10-17T13:00:00Z'}))
    (data/'auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':4,'by_sector':{'commercial':4,'mixed-use':0}}))
    catalogue=Catalogue(tmp_path)
    site=Site(catalogue, 'https://example.test')
    try:
        assert len(catalogue.properties)==3
        assert catalogue.properties[0]['id']==identity(current)
        rows={r['id']:r for r in catalogue.properties}
        for original in [withdrawn,prior]:
            row=rows[identity(original)]
            assert row['status']==original['status']
            assert not available_row(row)
            assert matches(row,'q=High+Street')
            assert matches(row,'status=unavailable')
            assert not matches(row,'status=available')
        pages=dict(site.routes())
        home=BeautifulSoup(pages['/'],'html.parser')
        metrics=[s.get_text(' ',strip=True) for s in home.select('.catalogue-strip > span')]
        assert metrics[:4]==['3 catalogue lots','1 available','2 sold / withdrawn / postponed','1 auction houses']
        assert home.select('.lot-status')[0].get_text(strip=True)=='WITHDRAWN · Unavailable'
        assert 'WITHDRAWN · Unavailable' in pages[rows[identity(withdrawn)]['path']]
        assert withdrawn['address'] not in pages['/deals/']
        assert len(site.upcoming)==1 and site.upcoming[0]['count']==1
        assets=dict(site.board_assets())
        index=json.loads(assets[f'/board/{site.board_version}/index.json'])
        assert {r['id'] for r in index['rows']}==set(rows)
        assert sum(not r['unavailable'] for r in index['rows'])==1
    finally:
        catalogue.close()


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
