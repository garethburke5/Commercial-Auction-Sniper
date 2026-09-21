from bs4 import BeautifulSoup
from collectors.bidx1 import _image_from_detail
from collectors.symonds_sampson import _image,_property_text,_brochure_links


def test_bidx1_uses_source_photo_zero_before_a_slick_clone_or_agent():
    html='''<meta property="og:image" content="https://images-prd.bidx1.com/images/surveyors/agent.jpg">
    <a data-pswp-photo-index="10" href="https://images-prd.bidx1.com/external/last_primary.jpg"><img alt="Property 11/11"></a>
    <a data-pswp-photo-index="0" href="https://images-prd.bidx1.com/external/first_primary.jpg"><img data-index="0" alt="Property 1/11"></a>'''
    assert _image_from_detail(BeautifulSoup(html,'lxml'),'https://bidx1.com/lot')=='https://images-prd.bidx1.com/external/first_primary.jpg'


def test_symonds_link_gallery_precedes_later_img_thumbnails():
    primary='https://cdn.webdadi.net/Media/image/l/66e1f440-c071-4942-a5f7-ad474d07f48b.jpg'
    html=f'''<a href="{primary}" title="Property Image"><div class="photo"></div></a>
    <img src="https://cdn.webdadi.net/Media/webp/s/fd06ccca-781f-47c8-9fa4-6a44c6c182eb.jpg" alt="Property Image">'''
    assert _image(BeautifulSoup(html,'lxml'),'https://auctions.symondsandsampson.co.uk/property/x')==primary


def test_symonds_viewing_form_before_h1_does_not_erase_particulars():
    html='''<nav>Commercial property</nav><div><h3>Arrange a viewing</h3><form>Name Email</form></div>
    <h1>West Street, Axminster</h1><h2>Guide Price £295,000</h2>
    <p>Mixed-use restaurant and three flats. Please refer to the brochure for further information.</p>
    <h3>Tenure: Freehold</h3><h3>Other properties you might be interested in</h3><p>Different property £1,000,000.</p>'''
    text=_property_text(BeautifulSoup(html,'lxml'))
    assert 'Mixed-use restaurant' in text and 'Freehold' in text
    assert 'Different property' not in text and 'Arrange a viewing' not in text


def test_brochure_query_string_is_preserved():
    s=BeautifulSoup('<a href="https://cdn.webdadi.net/Media/brochure.pdf?v=12">Brochure</a>','lxml')
    assert _brochure_links(s,'https://example.com')==['https://cdn.webdadi.net/Media/brochure.pdf?v=12']
