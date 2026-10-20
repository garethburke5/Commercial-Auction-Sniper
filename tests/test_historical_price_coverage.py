import sqlite3
from scripts.historical_price_coverage import coverage


def test_twenty_year_counts_do_not_invent_prices_or_complete_auctions():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE appearances(auctioneer,auction_id,auction_date,guide_price,sale_price,status)')
    db.executemany('INSERT INTO appearances VALUES (?,?,?,?,?,?)',[
        ('House A','a','2006-10-20',100,120,'sold'),
        ('House A','a','2006-10-20',200,None,'SOLD_PRIOR'),
        ('House A','b','2026-10-20',300,None,'unsold'),
        ('House B','b','2026-10-20','POA',0,'withdrawn'),
        ('House B','c','2026-10-20',None,None,'sold'),
        ('House A','old','2006-10-19',400,400,'sold'),
        ('House A','future','2026-10-21',400,400,'sold'),
        ('House A','unknown',None,400,400,'sold'),
    ])
    result=coverage(db,'2026-10-20')
    assert result['totals']['lot_appearances']==5
    assert result['totals']['auction_ids_observed']==4
    assert result['totals']['with_guide_price']==3
    assert result['totals']['with_sale_price']==1
    assert result['totals']['with_both_prices']==1
    assert result['totals']['marked_sold']==3
    assert result['totals']['marked_sold_without_sale_price']==2
    assert result['future_dated_appearances']==result['undated_appearances']==1
    assert not result['national_completeness_verified']
    assert result['by_auctioneer_and_year'][0]['auction_ids_observed']==1


def test_empty_corpus_has_zero_observations_not_asserted_complete_coverage():
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE appearances(auctioneer,auction_id,auction_date,guide_price,sale_price,status)')
    result=coverage(db,'2026-10-20')
    assert result['totals']['marked_sold']==0
    assert result['by_auctioneer_and_year']==[]
    assert not result['national_completeness_verified']
