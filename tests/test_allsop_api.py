import json
import pytest
from collectors.allsop_api import _catalogue, _detail, _day


def test_full_catalogue_traverses_pagination_and_rejects_false_completion():
    auction={'allsop_auctionid':'sale'}
    rows=[{'allsop_auctionid':'sale','allsop_lotid':str(i)} for i in range(152)]
    def get(path):
        part=rows[:100] if 'page=1' in path else rows[100:]
        return {'data':{'total':152,'results':part}}
    found,total,pages=_catalogue(auction,get)
    assert len(found)==total==152 and len(pages)==2
    with pytest.raises(ValueError,match='pagination stopped'):
        _catalogue(auction,lambda _: {'data':{'total':152,'results':rows[:100]}})


def test_public_detail_decimal_lot_number_featured_image_and_tenancy_schedule():
    row={'allsop_auctionid':'sale','allsop_lotid':'id1','allsop_lotnumber':1,'allsop_name':'C261001 155',
         'full_address':'108 Watling Street, Radlett, WD7 7AB','allsop_propertybyline':'Freehold Shop Investment',
         'allsop_propertytown':'Radlett','comm_property_types':['Retail'],'is_commercial':True}
    schedule={'headers':[{'key':'tenant','label':'Present Lessee'},{'key':'lease','label':'Lease Details'},
                         {'key':'rent','label':'Current Rent'},{'key':'review','label':'Next Review / Reversion'}],
              'rows':[{'tenant':'Occupational tenant','lease':'12 years from 21.10.2024. Break option 2031. FR&I',
                       'rent':'£39,000','review':'2029'}]}
    detail={'auction':{'date':'2026-10-06T23:00:00Z'},'version':dict(row,allsop_lotnumber='1.0000',
        allsop_propertytenure='Freehold',features=[{'value':'Shop investment. Total Current Rent Reserved £39,000 p.a.'}],
        lot={'guide_price_text':'£650,000–£675,000','guide_price_upper':675000,
             'current_rent_per_annum_header_text':'Total Current Rent Reserved','current_rent_per_annum_text':'£39,000 p.a.',
             'current_rent_per_annum':39000,'tenancy_table':json.dumps(schedule)}),
        'images':[{'file_id':'plan','type':'floorplan','sort_order':0},
                  {'file_id':'other','type':'gallery','sort_order':1},
                  {'file_id':'primary','type':'featured','sort_order':5}]}
    lot=_detail(row,lambda _:detail)
    assert lot.lot_number=='Lot 1' and lot.auction_date=='2026-10-07'
    assert lot.guide_price==650000 and lot.guide_price_upper==675000
    assert lot.annual_rent==39000 and lot.gross_yield==6
    assert lot.image_url=='https://www.allsop.co.uk/api/image/primary/884/497'
    assert lot.image_is_primary and lot.tenancy_schedule and lot.fri
    assert lot.tenant=='Occupational tenant' and '2031' in lot.break_clause
    # The real Totnes and Eastbourne catalogue entries omit their category flags.
    row.update(is_commercial=False,comm_property_types=[])
    assert _detail(row,lambda _:detail) is not None


def test_london_auction_day_respects_british_summer_time():
    assert _day('2026-10-06T23:00:00Z')=='2026-10-07'
