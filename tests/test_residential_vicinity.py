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
