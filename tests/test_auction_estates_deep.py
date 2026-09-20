import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import _property_content_text, _classified_property_type, _image, _needs_interactive


class AuctionEstatesDeepExtractionTests(unittest.TestCase):
    def test_unit_10_best_shop_primary_background_beats_later_floorplan(self):
        s=BeautifulSoup('''
        <div class="property-slideshow-container">
          <div class="propertySlides fade"><div class="lot-image"
            style="background-image: url('https://cdn.eigpropertyauctions.co.uk/ams/images/134/auction/3815/2862483_web_medium');"></div></div>
          <div class="propertySlides fade"><div class="lot-image"
            style="background-image: url('https://cdn.eigpropertyauctions.co.uk/ams/images/134/auction/3815/2872492_web_medium');"></div></div>
        </div>
        <img src="/media/floorplan.jpg" alt="Floor plan">
        ''','lxml')
        self.assertEqual(_image(s,'https://www.auctionestates.co.uk/property/unit-10-south-street-ilkeston-derbyshire-de75-5qe-364520'),
                         'https://cdn.eigpropertyauctions.co.uk/ams/images/134/auction/3815/2862483_web_medium')

    def test_page_chrome_is_excluded_from_property_particulars(self):
        s=BeautifulSoup('''
        <html><body>
          <h1>Unit 4 - 2 South Street, Ilkeston, DE7 5QE</h1>
          <div>Property Type Investment</div>
          <h3>Key Features</h3>
          <p>A retail investment property let to Hair & Beauty.</p>
          <p>Current Rent Reserved of £16,000.08 pa</p>
          <p>Offered For Sale on a new 999 year Long Leasehold (Virtual Freehold)</p>
          <h3>Important notices</h3>
          <p>The Conditions of Sale will be deposited at the offices of the auctioneers.</p>
        </body></html>
        ''','lxml')
        text=_property_content_text(s)
        self.assertIn('retail investment', text.lower())
        self.assertIn('999 year Long Leasehold', text)
        self.assertNotIn('offices of the auctioneers', text.lower())

    def test_investment_subtype_uses_lot_particulars_not_footer_office_wording(self):
        text='A retail investment property let to Hair & Beauty. Ground floor retail unit.'
        self.assertEqual(_classified_property_type('Investment',text),'Retail')

    def test_floorplan_is_not_selected_over_property_photo(self):
        s=BeautifulSoup('''
        <html><body><h1>Commercial Lot</h1>
          <img src="/media/plan123.jpg" alt="Floor plan" />
          <img src="/media/property364216.jpg" alt="Unit 4 - 2 South Street property photograph" />
        </body></html>
        ''','lxml')
        self.assertTrue(_image(s,'https://www.auctionestates.co.uk/property/unit-4-2-south-street-ilkeston-364216').endswith('property364216.jpg'))

    def test_interactive_fallback_is_requested_when_tabs_have_no_payload(self):
        s=BeautifulSoup('''
        <html><body><h1>Commercial Lot</h1><div>Details Tenure EPC</div><p>Retail investment opportunity</p></body></html>
        ''','lxml')
        self.assertTrue(_needs_interactive(s))

    def test_tabs_are_hydrated_even_when_visible_prose_mentions_tenure(self):
        s=BeautifulSoup('''
        <html><body><h1>Commercial Lot</h1><div>Details Tenure EPC</div>
        <div>Freehold mixed-use property with buyer information hidden behind the tabs.</div></body></html>
        ''','lxml')
        self.assertTrue(_needs_interactive(s))


if __name__=='__main__':
    unittest.main()
