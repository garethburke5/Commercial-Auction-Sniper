from pathlib import Path
from datetime import date
from unittest.mock import patch

from bs4 import BeautifulSoup

from collectors import auction_house_london_resilient as ahl
from collectors.core import Lot
from collectors.financials import income_facts
from collectors.publication_quality import commercial_decision
from collectors.pugh import _page_targets, _parse_detail, _lot_no
from property_summary import build_opportunity_summary

FIXTURES=Path(__file__).parent/'fixtures'
PERCY='https://www.pugh-auctions.com/property/202607231641sq_tkoe'

def test_pugh_all_lots_are_discovered_without_teaser_keywords():
    page=BeautifulSoup((FIXTURES/'pugh_catalogue_table.html').read_text(),'lxml')
    targets=_page_targets(page,'2026-09-26')
    assert len(targets)==20
    assert targets[PERCY][1] is None
    assert targets[PERCY][2]=='2026-10-28'
    assert _lot_no('15 - 23 Percy Street') is None
    assert _lot_no('Lot 048 The Woollen Pig, 160 Duke Street')=='Lot 048'

def test_pugh_own_particulars_not_costs_or_neighbouring_lots():
    page=BeautifulSoup((FIXTURES/'pugh_percy_street.html').read_text(),'lxml')
    lot=_parse_detail(page,PERCY)
    assert lot.guide_price==225000 and lot.annual_rent==29000
    assert lot.auction_date=='2026-10-28' and lot.status=='CURRENT'
    assert lot.lot_number is None
    assert lot.area_sqft is None  # 1,984 sq ft describes just Number 15.
    assert lot.property_type=='Retail' and lot.image_is_primary
    assert '1_t202607281426__2__t202607281543.jpg' in lot.image_url
    assert '3.6%' not in lot.description

def test_ahl_classifies_details_even_without_commercial_teaser():
    index=BeautifulSoup('<h1>7th October 2026</h1><article><a href="/lot/unlabelled">55A North Street</a></article><article><a href="/lot/house">1 High Street</a></article>','lxml')
    def detail(source,url,**kw):
        description='Ground floor retail unit let to Betfred.' if url.endswith('unlabelled') else 'A two-bedroom terraced house. Location: Shops and supermarket nearby. Accommodation: Two bedrooms.'
        return Lot(source,url,'North Street' if url.endswith('unlabelled') else '1 High Street',auction_date='2026-10-07',description=description,status='CURRENT')
    stats={}
    with patch.object(ahl,'soup',return_value=index),patch.object(ahl,'detail_lot',side_effect=detail), patch.object(ahl.base,'date',wraps=date) as clock:
        clock.today.return_value=date(2026,10,7)
        lots,dates,failures,discovered=ahl._collect_page(ahl.CURRENT,reconciliation=stats)
    assert discovered==2 and failures==0 and len(lots)==1
    assert stats['detail_pages_inspected']==2 and stats['noncommercial_excluded']==1

def test_mixed_use_road_does_not_make_a_house_mixed_use():
    assert commercial_decision({'address':'26 Bluecoat Close','description':'A two-bedroom house on a mixed use road.'}) is False

def test_source_retail_type_wins_over_possible_office_use():
    title,_=build_opportunity_summary({'property_type':'Retail','occupation':'Vacant','description':'Retail premises which may suit office use.'})
    assert title=='VACANT RETAIL OPPORTUNITY'

def test_stated_current_income_wins_over_agreed_future_increase():
    text='Currently producing £69,850 per annum, due to increase to £76,958 per annum. An offer has been accepted, annual rent £7,108.08, thus bringing the new total rent to £76,958 per annum.'
    assert income_facts(text)['annual_rent']==69850
