import unittest
from bs4 import BeautifulSoup

from collectors.town_country import _discover_from_page, _is_target_text, _property_key


class TownCountryCollectorTests(unittest.TestCase):
    def test_current_commercial_and_mixed_use_cards_are_discovered(self):
        html='''
        <main>
          <article>
            <h3>Online: Lot 26 | End Time - 23/09/2026 14:00</h3>
            <a href="/lot/details/80026">80-82 High Street, Littlehampton, West Sussex, BN17 5DX</a>
            <h4>Commercial Investment/Development Opportunity</h4>
            <p>Substantial double-fronted property extending to 4,287 sq ft.</p>
            <p>Guide Price*: £300,000</p>
          </article>
          <article>
            <h3>Online: Lot 27 | End Time - 23/09/2026 14:05</h3>
            <a href="/lot/details/80027">37/39 Baker Street, Weybridge, Surrey, KT13 8AE</a>
            <h4>Freehold Mixed Use Property</h4>
            <p>Ground-floor retail unit with a two-bedroom apartment.</p>
            <p>Guide Price*: £520,000</p>
          </article>
          <article>
            <h3>Online: Lot 3 | End Time - 23/09/2026 12:05</h3>
            <a href="/lot/details/80003">Flat 15 Oakland Court, Worthing, BN12 5AR</a>
            <p>Two bedroom retirement apartment. Guide Price*: £90,000</p>
          </article>
        </main>
        '''
        found=_discover_from_page('https://london.townandcountrypropertyauctions.co.uk',BeautifulSoup(html,'lxml'),today='2026-09-07')
        self.assertEqual(len(found),2)
        self.assertTrue(any('80026' in u for u in found))
        self.assertTrue(any('80027' in u for u in found))

    def test_past_commercial_card_is_not_live(self):
        html='''<article><h3>Online: Lot 2 | Auction Ended - 18/08/2026 10:02</h3>
        <a href="/lot/details/70002">102 Islington High Street, London, N1 8EG</a>
        <p>Freehold Commercial Property over Two Floors Result: Sold Prior Guide Price*: £500,000</p></article>'''
        found=_discover_from_page('https://london.townandcountrypropertyauctions.co.uk',BeautifulSoup(html,'lxml'),today='2026-09-07')
        self.assertEqual(found,{})

    def test_commercial_floor_space_and_office_are_target_evidence(self):
        self.assertTrue(_is_target_text('Consented scheme with 228 sqm of ground floor commercial floor space (Use Class E).'))
        self.assertTrue(_is_target_text('A Detached Office Building subject to an Occupational Lease.'))

    def test_regional_mirrors_share_one_property_key(self):
        a='https://london.townandcountrypropertyauctions.co.uk/lot/details/80026'
        b='https://www.townandcountrypropertyauctions.co.uk/lot/details/80026'
        self.assertEqual(_property_key(a),_property_key(b))


if __name__=='__main__':
    unittest.main()
