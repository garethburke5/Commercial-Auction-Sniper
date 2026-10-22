from coverage_metrics import source_metrics


def test_historical_labels_are_counted_without_reassigning_acquired_brands():
    snapshot={'source_health':[{'source':n,'status':'LIVE'} for n in ('Allsop Commercial','Pugh / BTG Eddisons','SDL Property Auctions')]}
    history={'by_auctioneer':{'Allsop':100,'Allsop Commercial':3,'Pugh Auctioneers':20,'BTG Eddisons':5,'SDL Property Auctions':7}}
    original=dict(history['by_auctioneer'])
    rows={r['source']:r for r in source_metrics(snapshot,history,{})}
    assert rows['Allsop Commercial']['historical_records']==103
    assert rows['Pugh / BTG Eddisons']['historical_records']==25
    assert rows['SDL Property Auctions']['historical_records']==7
    assert history['by_auctioneer']==original


def test_source_property_headings_do_not_leave_stray_the_bullets():
    from web_platform.particulars import structured_particulars
    row={'description':'THE PROPERTY: THE GARAGE: A freehold rank of 4 single garages. THE OPPORTUNITY: Sold with vacant possession.'}
    items=[v for s in structured_particulars(row) for v in s['items']]
    assert 'THE' not in items
    assert any('4 single garages' in v for v in items)
    assert any('vacant possession' in v for v in items)
    assert not any('THE OPPORTUNITY:' in v or 'THE GARAGE:' in v for v in items)


def test_free_snapshot_retains_the_asset_description_with_freehold_wording():
    from web_platform.free_snapshot import snapshot_particulars
    row={'tenure':'Freehold','description':'THE PROPERTY: A Freehold mid terraced commercial building with accommodation of 980 Sq Ft arranged over two floors including a basement. THE OPPORTUNITY: The property is let at £16,200 per annum.'}
    sections=snapshot_particulars(row)
    property_text=' '.join(next(s['items'] for s in sections if s['title']=='The property'))
    assert '980 Sq Ft' in property_text and 'two floors' in property_text
    assert 'THE.' not in property_text
