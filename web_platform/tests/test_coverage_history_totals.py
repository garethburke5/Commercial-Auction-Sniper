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
