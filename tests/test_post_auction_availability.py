from datetime import datetime, timedelta, timezone, date

from board_presentation import current_board_row, verified_post_auction_available, available_row
from collectors.allsop_api import _auction_targets, _detail
from run_collectors import _auction_has_finished, _merge_last_good


def evidence(**extra):
    return dict(source='Allsop Commercial', status='CURRENT', auction_date='2026-10-07',
                source_availability='Available', availability_checked_at=datetime.now(timezone.utc).isoformat()) | extra


def test_past_date_needs_fresh_explicit_availability():
    row=evidence()
    assert current_board_row(row, date(2026,10,17))
    assert available_row(row, date(2026,10,17))
    assert not _auction_has_finished(row,date(2026,10,17))
    for changes in [dict(source_availability=None),dict(availability_checked_at=None),
                    dict(source='Another auctioneer'),dict(status='SOLD'),dict(status='WITHDRAWN'),
                    dict(availability_checked_at=(datetime.now(timezone.utc)-timedelta(hours=15)).isoformat()),
                    dict(availability_checked_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()),
                    dict(availability_checked_at='2026-10-17T12:00:00')]:
        changed=row|changes
        assert not verified_post_auction_available(changed)
        assert not current_board_row(changed,date(2026,10,17))
        assert _auction_has_finished(changed,date(2026,10,17))


def test_new_source_status_overrides_old_withdrawn_without_changing_identity():
    old=evidence(status='WITHDRAWN',url='https://www.allsop.co.uk/lot-overview/example/c261001-215',lot_number='Lot 77')
    new=old|evidence()
    merged=_merge_last_good(old,new)
    assert merged['status']=='CURRENT'
    assert merged['lot_number']=='Lot 77' and merged['auction_date']=='2026-10-07'
    assert not _auction_has_finished(merged,date(2026,10,17))
    unknown=_merge_last_good(merged,new|{'source_availability':None})
    assert not verified_post_auction_available(unknown)


def test_recent_catalogues_are_checked_including_residential_mixed_use():
    def sale(id,day,name='Auction'):
        return {'allsop_auctionid':id,'allsop_auctiondate':day,'allsop_name':name}
    upcoming=sale('next','2026-11-11')
    recent=sale('oct','2026-10-06T23:00:00Z')
    past={'commercial':[recent,sale('old','2026-07-15'),sale('test','2026-10-01','Test Auction')],
          'residential':[sale('resi','2026-09-17')]}
    targets=_auction_targets({'next_commercial_auction':upcoming},past,date(2026,10,17))
    assert [(s['allsop_auctionid'],department) for s,department in targets]==[
        ('next','commercial'),('oct','commercial'),('resi','residential')]


def test_missing_detail_status_cannot_claim_post_auction_availability():
    row={'allsop_auctionid':'sale','allsop_lotid':'lot','allsop_lotnumber':77,
         'allsop_name':'C261001 215','full_address':'182 Barrack Road',
         'allsop_propertybyline':'Freehold shop investment','is_commercial':True,'lot_status':'Available'}
    detail={'auction':{'date':'2026-10-07'},'version':dict(row,features=[{'value':'Shop investment with flat above'}],lot={})}
    lot=_detail(row,lambda _:detail)
    assert lot.source_availability is None
    assert not verified_post_auction_available(lot.to_dict())
    detail['version']['allsop_lotstatus']='Available'
    lot=_detail(row,lambda _:detail)
    assert verified_post_auction_available(lot.to_dict())
    detail['version']['allsop_lotstatus']='Sold After'
    lot=_detail(row,lambda _:detail)
    assert lot.status=='SOLD' and lot.source_availability=='SOLD AFTER'
    assert not verified_post_auction_available(lot.to_dict())


def test_available_after_auction_is_searchable_without_changing_url(tmp_path):
    import json
    from web_platform.catalogue import Catalogue, identity
    from web_platform.board import index_row
    row=evidence(address='182 & 182a Barrack Road, Christchurch, Dorset, BH23 2BQ',
                 url='https://www.allsop.co.uk/lot-overview/example/c261001-215',
                 lot_number='Lot 77',auction_id='sale',guide_price=575000,annual_rent=53800,
                 description='Restaurant takeaway and residential investment',tenure='Freehold')
    (tmp_path/'data/auction_history').mkdir(parents=True)
    (tmp_path/'data/auction_history/progress.json').write_text('{}')
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[row],'archive':[], 'generated_at':row['availability_checked_at']}))
    catalogue=Catalogue(tmp_path,summaries=False)
    try:
        assert len(catalogue.properties)==1
        found=catalogue.properties[0]
        assert found['id']==identity(row|{'status':'WITHDRAWN'})
        assert found['post_auction_available']
        assert 'bh23' in index_row(found,0)['search_text']
        assert not found['unavailable']
    finally:catalogue.close()
