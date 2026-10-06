from collectors.publication_quality import commercial_decision

def test_domestic_accommodation_and_village_amenities_do_not_create_commercial_stock():
 for text in [
  'Vacant Two Bedroom Mid Terrace Cottage. Lounge, kitchen, two bedrooms. Located in the charming village of Ribchester which benefits from cafés and a post office/general store.',
  'Vacant Ground Floor One Bedroom Flat. Kitchen, lounge, bedroom and bathroom. The flat is a short walk from shops, café’s and transport links.',
  'Three-Bedroom Semi Detached Listed Farmhouse. Ground floor kitchen/diner, two reception rooms, office space and WC. First floor three bedrooms with ensuites.'
 ]:
  assert commercial_decision({'description':text}) is False

def test_current_shop_with_residential_accommodation_remains_mixed_use():
 assert commercial_decision({'description':'A ground floor shop investment with a two bedroom flat above, located in the village centre.'}) is True
 assert commercial_decision({'description':'A commercial office building with a two bedroom flat above.'}) is True


def test_former_commercial_name_is_not_current_commercial_evidence():
 for text in [
  'A two bedroom terraced property. Forming part of a former public house conversion, this spacious two-bedroom home has its own entrance.',
  'Site of Former Panorama Hotel. Offered with full planning permission for a 20-apartment residential scheme.',
  'Land at the rear of former Golden Ball Hotel. A freehold residential development site with permission for 18 dwellings.',
  'A four bedroom townhouse. Chester Cathedral, Storyhouse, the River Dee, Grosvenor Shopping Centre and Chester Racecourse are all within easy reach.'
 ]:
  assert commercial_decision({'description':text}) is False
