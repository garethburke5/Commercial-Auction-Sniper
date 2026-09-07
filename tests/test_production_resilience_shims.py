import unittest

from bs4 import BeautifulSoup

from collectors.symonds_sampson_resilient import _event_card_text
from collectors.future_property_auctions_resilient import _exact_detail_image


class ProductionResilienceShimTests(unittest.TestCase):
    def test_symonds_duplicate_links_to_same_event_do_not_hide_date(self):
        html = '''
        <div class="event-card">
          <p>Thursday, 24 September 2026 2:00 PM - 5:00 PM</p>
          <a href="/event/property-auction-sep2026-memorialhall">Property Auction</a>
          <a href="/event/property-auction-sep2026-memorialhall#details">View Event</a>
        </div>
        '''
        s = BeautifulSoup(html, "lxml")
        text = _event_card_text(s.find("a"))
        self.assertIn("24 September 2026", text)

    def test_fpa_exact_detail_page_accepts_scoped_upload_without_public_id(self):
        html = '''
        <html><body>
          <img src="/images/logo.png" alt="Logo">
          <img src="/upload/glasgow_shop_front_IMG_00.jpg" alt="Property exterior">
          <img src="/upload/floorplan.jpg" alt="Floor plan">
        </body></html>
        '''
        s = BeautifulSoup(html, "lxml")
        image = _exact_detail_image(
            s,
            "https://www.futurepropertyauctions.co.uk/property_details.asp?id=14511812",
        )
        self.assertEqual(
            image,
            "https://www.futurepropertyauctions.co.uk/upload/glasgow_shop_front_IMG_00.jpg",
        )


if __name__ == "__main__":
    unittest.main()
