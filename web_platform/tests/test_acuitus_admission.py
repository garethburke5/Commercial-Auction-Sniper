from bs4 import BeautifulSoup
import pytest
from scripts.harvest_acuitus_canonical import Bank,parse_results,commercial_sector,all_results_request,incomplete_years,collection_summary
from scripts import harvest_acuitus_canonical as canonical

def test_full_catalogue_request_overrides_archive_default_without_mutating_input():
    auction={'base_fields':{'which':'results','perpage':'128'}}
    request=all_results_request(auction)
    assert request['base_fields']['perpage']=='1000'
    assert auction['base_fields']['perpage']=='128'

def test_retry_appends_new_lots_without_replacing_existing_shard(tmp_path,monkeypatch):
    monkeypatch.setattr(canonical.corpus,'DATA',tmp_path)
    first=canonical.corpus.base_row('Acuitus','acuitus:2016-10-13','2016-10-13','1','1','https://www.acuitus.co.uk/property/1/')
    second=canonical.corpus.base_row('Acuitus','acuitus:2016-10-13','2016-10-13','2','2','https://www.acuitus.co.uk/property/2/')
    canonical.corpus.write_rows('commercial-expansion/acuitus-2016-10-13',[first])
    bank=Bank()
    bank.admit(second,'commercial-expansion/acuitus-2016-10-13')
    bank.flush()
    shard=tmp_path/'appearances/commercial-expansion/acuitus-2016-10-13.jsonl.gz'
    assert {row['source_lot_id'] for row in canonical.corpus.iter_rows(shard)}=={'1','2'}

def test_resume_selects_only_years_with_unreconciled_discovered_sales(tmp_path,monkeypatch):
    monkeypatch.setattr(canonical.corpus,'DATA',tmp_path)
    canonical.corpus.save_json(tmp_path/'auctions/commercial-expansion/acuitus-2020-02-12.json',{'catalogue_complete':True})
    auctions=[{'auction_date':'2020-02-12'},{'auction_date':'2021-02-11'},{'auction_date':'2021-03-25'}]
    assert incomplete_years(auctions)==[2021]

def test_collection_summary_reconciles_discovered_catalogues(tmp_path,monkeypatch):
    monkeypatch.setattr(canonical.corpus,'DATA',tmp_path)
    for date,count in [('2020-02-12',10),('2021-02-11',12)]:
        canonical.corpus.save_json(tmp_path/f'auctions/commercial-expansion/acuitus-{date}.json',
            {'auction_date':date,'catalogue_complete':True,'expected_public_results':count,'lots_captured':count})
    summary=collection_summary([{'auction_date':'2020-02-12'},{'auction_date':'2021-02-11'}])
    assert summary['complete'] and summary['catalogues_complete']==2
    assert summary['published_lot_rows']==summary['captured_lot_rows']==22

def test_results_preserve_terminal_and_financial_meanings():
    html='<p>1 - 3 of 3 properties</p>'
    html+='<a href="javascript:void(0)"><span class="proplist-grid-address">Watch list control</span><dl class="proplist-grid-status"><dt>Status</dt><dd>Sold</dd></dl></a>'
    for n,status,label,price,kind in [(1,'Sold','Price*','£80,000','High Street Retail'),(2,'Sold Prior','Price*','','Retail, Residential'),(3,'Available','Guide*','£25,000 - £50,000','Residential')]:
        href='https://www.acuitus.co.uk/property/' if n==1 else f'https://www.acuitus.co.uk/property/{n}/'
        html+=f'<a href="{href}"><span class="proplist-grid-address">{n} High Street<br>London<br>SW1A 1AA</span><span class="proplist-sector">{kind}</span><dl class="proplist-grid-status"><dt>Auction</dt><dd>21/07/2021</dd><dt>Lot</dt><dd>{n}</dd><dt>Status</dt><dd>{status}</dd><dt>{label}</dt><dd>{price}</dd></dl></a>'
    rows,expected,complete=parse_results(BeautifulSoup(html,'html.parser'),'2021-07-21',{})
    assert complete and expected==len(rows)==3
    assert rows[0]['sale_price']==80000 and rows[0]['guide_price'] is None
    assert rows[0]['source_lot_id']=='lot-1' and rows[0]['source_card_href'].endswith('/property/')
    assert rows[1]['sale_price'] is None and rows[1]['status']=='sold prior' and rows[1]['sector']=='mixed-use'
    assert rows[2]['guide_price']==25000 and rows[2]['guide_price_high']==50000 and rows[2]['sale_price'] is None
    assert rows[2]['sector']=='residential'
    assert not parse_results(BeautifulSoup(html.replace('3 of 3','3 of 50'),'html.parser'),'2021-07-21',{})[2]
    with pytest.raises(ValueError):parse_results(BeautifulSoup(html,'html.parser'),'2020-07-21',{})
