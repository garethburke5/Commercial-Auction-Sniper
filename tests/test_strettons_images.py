from bs4 import BeautifulSoup

from collectors.utils import image_from_soup


def test_strettons_embedded_gallery_image_wins_over_generic_images():
    html = r'''
    <html><head><meta property="og:image" content="https://www.strettons.co.uk/assets/staff/jane.jpg"></head>
    <body>
      <img src="https://www.strettons.co.uk/assets/logo.png">
      <script>
        window.__PROPERTY__ = {"images":["https:\/\/ggfx-strettons.s3.eu-west-2.amazonaws.com\/i\/api_sources\/abc123\/images\/hero_web_medium.jpeg"]};
      </script>
    </body></html>
    '''
    soup = BeautifulSoup(html, "lxml")
    image = image_from_soup(
        soup,
        "https://www.strettons.co.uk/auction-commercial-property-for-sale/example/",
    )
    assert image == "https://ggfx-strettons.s3.eu-west-2.amazonaws.com/i/api_sources/abc123/images/hero_web_medium.jpeg"


def test_non_strettons_image_selection_is_unchanged():
    html = '<html><head><meta property="og:image" content="https://example.com/property.jpg"></head></html>'
    soup = BeautifulSoup(html, "lxml")
    assert image_from_soup(soup, "https://example.com/lot/1") == "https://example.com/property.jpg"
