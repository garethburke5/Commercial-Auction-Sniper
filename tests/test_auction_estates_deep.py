import unittest
from bs4 import BeautifulSoup

from collectors.auction_estates import _property_content_text, _classified_property_type, _image, _needs_interactive


class AuctionEstatesDeepExtractionTests(unittest.TestCase):
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
        <html><body>
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

    def test_static_hidden_tenure_avoids_unnecessary_browser_clicks(self):
        s=BeautifulSoup('''
        <html><body><h1>Commercial Lot</h1><div>Details Tenure EPC</div>
        <div style="display:none">Offered For Sale on a new 999 year Long Leasehold (Virtual Freehold)</div></body></html>
        ''','lxml')
        self.assertFalse(_needs_interactive(s))


if __name__=='__main__':
    unittest.main()
