import unittest
from bs4 import BeautifulSoup

from collectors.barnett_ross import _property_image


class BarnettRossImageTests(unittest.TestCase):
    def test_linked_photo1_original_beats_logo_and_thumbnail(self):
        s=BeautifulSoup('''
        <html><body>
          <img src="/images/logo.png" alt="Barnett Ross Logo">
          <a href="/details/20260910/1.jpg"><img src="/details/20260910/thumb1.jpg" alt="Photo1"></a>
          <a href="/details/20260910/2.jpg"><img src="/details/20260910/thumb2.jpg" alt="Photo2"></a>
        </body></html>
        ''','lxml')
        self.assertEqual(
            _property_image(s,'https://www.barnettross.co.uk/property.php?id=4872925'),
            'https://www.barnettross.co.uk/details/20260910/1.jpg',
        )


if __name__=='__main__':
    unittest.main()
