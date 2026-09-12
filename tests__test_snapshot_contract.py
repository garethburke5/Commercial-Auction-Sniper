
from collectors__core import Lot

def test_yield_is_calculated_not_scraped():
    lot=Lot(source="X",url="https://example.com/1",address="A",
            guide_price=150000,annual_rent=20000,gross_yield=99).finalise()
    assert lot.gross_yield == 13.33

def test_missing_rent_means_unknown_yield():
    lot=Lot(source="X",url="https://example.com/2",address="B",
            guide_price=150000,annual_rent=None).finalise()
    assert lot.gross_yield is None
