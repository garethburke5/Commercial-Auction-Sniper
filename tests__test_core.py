
from collectors__core import is_commercial, parse_guide, parse_rent

def test_commercial_positive():
    assert is_commercial("Freehold commercial investment comprising a retail unit")
    assert is_commercial("Mixed use property with ground floor shop and flat above")

def test_residential_negative():
    assert not is_commercial("Three-bedroom semi-detached house with garden")
    assert not is_commercial("Residential flat producing £12,000 pa")

def test_financial_parsing():
    assert parse_guide("Guide Price £135,000") == 135000
    assert parse_rent("Investment Let at £15,000 pa") == 15000
