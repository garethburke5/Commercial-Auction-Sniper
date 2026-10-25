import scripts.harvest_barnard_marcus as collector


def test_reconciled_search_inventory_declares_standard_catalogue_completeness(monkeypatch):
    monkeypatch.setattr(collector, "parse_ids", lambda _url: ("house", "auction"))
    monkeypatch.setattr(collector, "fetch_json", lambda _url: {
        "pagination": {"pageCount": 1, "currentPage": 1, "totalCount": 1},
        "items": [{
            "id": 42,
            "lotNumber": "1",
            "addressLine1": "1 High Street",
            "addressLine2": "London, SW1A 1AA",
            "description": "A residential and commercial mixed-use property",
            "priceDescriptor": "Sold for",
            "price": "£250,000",
            "showPriceAsterix": False,
            "statusLabel": "Sold",
            "url": "https://www.barnardmarcusauctions.co.uk/auctions/example/42/",
            "image": "/media/example.jpg",
        }],
    })

    payload = collector.harvest(
        "https://www.barnardmarcusauctions.co.uk/auctions/example/",
        "2026-02-03",
    )

    assert payload["catalogue_complete"] is True
    assert payload["catalogue_lot_count"] == 1
    assert payload["published_rows"] == payload["source_reported_rows"] == 1
    assert payload["reconciliation_shortfall"] == 0
    assert payload["lot_records"][0]["source_record_id"] == "barnard-marcus-property:42"
    assert payload["lot_records"][0]["result_price_gbp"] == 250_000


def test_unsold_price_cannot_become_sale_amount(monkeypatch):
    monkeypatch.setattr(collector,'parse_ids',lambda u:('house','auction'))
    monkeypatch.setattr(collector,'fetch_json',lambda u:{'pagination':{'pageCount':1,'currentPage':1,'totalCount':1},'items':[{'id':42,'lotNumber':'1','addressLine1':'1 High Street','priceDescriptor':'Unsold','price':'£250,000','statusLabel':'Unsold'}]})
    row=collector.harvest('https://example.com/','2026-02-03')['lot_records'][0]
    assert row['result_price_gbp'] is None


def test_changing_source_total_retains_valid_lots_without_claiming_complete(monkeypatch):
    monkeypatch.setattr(collector, 'parse_ids', lambda u: ('house','auction'))
    def fetch(url):
        page=int(url.rsplit('=',1)[1])
        return {'pagination':{'pageCount':2,'currentPage':page,'totalCount':2 if page==1 else 3},
                'items':[{'id':page,'lotNumber':str(page),'addressLine1':f'{page} High Street'}]}
    monkeypatch.setattr(collector,'fetch_json',fetch)
    payload=collector.harvest('https://example.com/','2026-10-15',allow_incomplete=True)
    assert payload['published_rows']==2
    assert payload['catalogue_complete'] is False
    assert payload['source_reported_totals']==[2,3]
    assert payload['reconciliation_shortfall']==1
    assert payload['reconciliation_errors']


def test_wrong_page_identity_is_rejected_even_in_partial_mode(monkeypatch):
    import pytest
    monkeypatch.setattr(collector,'parse_ids',lambda u:('house','auction'))
    monkeypatch.setattr(collector,'fetch_json',lambda u:{'pagination':{'pageCount':2,'currentPage':1,'totalCount':2},'items':[{'id':1}]})
    with pytest.raises(RuntimeError,match='different page identity'):
        collector.harvest('https://example.com/','2026-10-15',allow_incomplete=True)


def test_page_checkpoint_reuses_source_payload_and_refreshes_after_expiry(monkeypatch,tmp_path):
    calls=[]
    monkeypatch.setattr(collector.time,'time',lambda:100000)
    monkeypatch.setattr(collector,'fetch_json',lambda url:calls.append(url) or {'items':[{'id':42}]})
    url='https://example.com/api?page=2'
    assert collector.fetch_json_cached(url,tmp_path)=={'items':[{'id':42}]}
    assert collector.fetch_json_cached(url,tmp_path)=={'items':[{'id':42}]}
    assert calls==[url]
    monkeypatch.setattr(collector.time,'time',lambda:121601)
    collector.fetch_json_cached(url,tmp_path)
    assert calls==[url,url]


def test_sitemap_recovers_missing_identity_and_preserves_api_variance(monkeypatch):
    payload={'catalogue_complete':False,'lot_records':[{'source_record_id':'barnard-marcus-property:1'}],
             'source_url':'https://example.com/auction/','auction_date':'2026-10-15','source_reported_rows':3,
             'reconciliation_errors':['API total changed during traversal']}
    monkeypatch.setattr(collector,'sitemap_lot_urls',lambda u:['https://example.com/auction/1/','https://example.com/auction/2/'])
    monkeypatch.setattr(collector,'item_from_lot_page',lambda u:{'id':2,'lotNumber':'2','addressLine1':'2 High Street'})
    result=collector.recover_sitemap_rows(payload)
    assert result['published_rows']==2
    assert result['sitemap_recovery']['rows_recovered']==1
    assert result['reconciliation_shortfall']==0
    assert result['catalogue_complete'] is True
    assert result['search_api_variance_errors']


def test_exact_sitemap_identity_set_reconciles_unstable_api_totals(monkeypatch):
    payload={
        'catalogue_complete':False,
        'lot_enumeration_complete':False,
        'lot_records':[
            {'source_record_id':'barnard-marcus-property:1'},
            {'source_record_id':'barnard-marcus-property:2'},
        ],
        'source_url':'https://example.com/auction/',
        'auction_date':'2026-10-15',
        'source_reported_rows':3,
        'catalogue_lot_count':3,
        'reconciliation_errors':['page 2 reports 3 lots; first page reports 2'],
    }
    urls=['https://example.com/auction/1/','https://example.com/auction/2/']

    result=collector.recover_sitemap_rows(payload,lot_urls=urls)

    assert result['catalogue_complete'] is True
    assert result['lot_enumeration_complete'] is True
    assert result['published_rows']==result['source_reported_rows']==result['catalogue_lot_count']==2
    assert result['reconciliation_shortfall']==0
    assert result['reconciliation_errors']==[]
    assert result['search_api_variance_errors']==['page 2 reports 3 lots; first page reports 2']
    assert result['sitemap_recovery']['exact_identity_match'] is True


def test_sitemap_identity_reconciliation_rejects_extra_saved_row():
    payload={
        'catalogue_complete':False,
        'lot_records':[
            {'source_record_id':'barnard-marcus-property:1'},
            {'source_record_id':'barnard-marcus-property:999'},
        ],
        'source_url':'https://example.com/auction/',
        'auction_date':'2026-10-15',
        'source_reported_rows':2,
    }
    urls=['https://example.com/auction/1/']

    result=collector.recover_sitemap_rows(payload,lot_urls=urls)

    assert result.get('catalogue_complete') is False
    assert result['sitemap_recovery']['exact_identity_match'] is False
    assert result['sitemap_recovery']['rows_not_in_sitemap']==['barnard-marcus-property:999']
