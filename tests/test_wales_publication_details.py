from pathlib import Path
from bs4 import BeautifulSoup
from collectors.auction_house_regions import _direct_first_party_lot
from run_collectors import QUALITY_FACT_FIELDS, _meaningful


def test_modern_wales_particulars_reach_the_publication_quality_producer():
    page=BeautifulSoup((Path(__file__).parent/'fixtures/auction_house_wales_rhymney.html').read_text(),'lxml')
    lot=_direct_first_party_lot('Auction House Wales','https://wales.auctionhouse.co.uk/lot/redirect/366748',
        '*Guide | £98,000 (plus fees) 3 Bed Commercial Property 67 High Street, Rhymney, Caerphilly, NP22 5LP',
        '67 High Street, Rhymney, Caerphilly, NP22 5LP',None,'2026-10-07',fetcher=lambda _:page)
    assert lot.address=='67 High Street, Rhymney, Caerphilly, NP22 5LP'
    assert lot.guide_price==98000
    assert lot.tenure=='Freehold'
    assert lot.property_type=='Mixed Use'
    assert lot.occupation=='Vacant' and lot.annual_rent is None and lot.gross_yield is None
    assert lot.area_sqm==250
    assert lot.epc=='Commercial - E - Residential - D'
    assert lot.image_is_primary and '/2886040_web_medium' in lot.image_url
    assert lot.url.endswith('/12158d2d-10b7-4297-ae50-ea83fd20f325')
    assert 'Log In' not in lot.description and 'Buyers Premium' not in lot.description
    assert sum(_meaningful(lot.to_dict().get(k)) for k in QUALITY_FACT_FIELDS)>=4
