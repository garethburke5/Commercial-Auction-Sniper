from bs4 import BeautifulSoup
import pytest
from scripts.harvest_acuitus_canonical import parse_results,commercial_sector

def test_results_preserve_terminal_and_financial_meanings():
    html='<p>1 - 3 of 3 properties</p>'
    for n,status,label,price,kind in [(1,'Sold','Price*','£80,000','High Street Retail'),(2,'Sold Prior','Price*','','Retail, Residential'),(3,'Available','Guide*','£25,000 - £50,000','Residential')]:
        html+=f'<a href="https://www.acuitus.co.uk/property/{n}/"><span class="proplist-grid-address">{n} High Street<br>London<br>SW1A 1AA</span><span class="proplist-sector">{kind}</span><dl class="proplist-grid-status"><dt>Auction</dt><dd>21/07/2021</dd><dt>Lot</dt><dd>{n}</dd><dt>Status</dt><dd>{status}</dd><dt>{label}</dt><dd>{price}</dd></dl></a>'
    rows,expected,complete=parse_results(BeautifulSoup(html,'html.parser'),'2021-07-21',{})
    assert complete and expected==len(rows)==3
    assert rows[0]['sale_price']==80000 and rows[0]['guide_price'] is None
    assert rows[1]['sale_price'] is None and rows[1]['status']=='sold prior' and rows[1]['sector']=='mixed-use'
    assert rows[2]['guide_price']==25000 and rows[2]['guide_price_high']==50000 and rows[2]['sale_price'] is None
    assert rows[2]['sector']=='residential'
    assert not parse_results(BeautifulSoup(html.replace('3 of 3','3 of 50'),'html.parser'),'2021-07-21',{})[2]
    with pytest.raises(ValueError):parse_results(BeautifulSoup(html,'html.parser'),'2020-07-21',{})
