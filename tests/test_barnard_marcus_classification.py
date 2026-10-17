import json
import unittest
from datetime import date
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from collectors.barnard_marcus import _is_target_particulars, _sale_summary, _parse_detail, _advertised_dates, _discover, _available_urls, collect
from collectors.publication_quality import publication_exclusion
from board_presentation import verified_post_auction_available


def page(summary, price='Guide Price £70,000–£80,000'):
    return BeautifulSoup(f'''<html><title>22, Auction: 15th October 2026.</title>
        <h1>59 Norfolk Street, Wisbech</h1>
        <div class="lot-details__price">{price} Tenure: Freehold</div>
        <div class="lot-details__gallery-carousel">
          <div class="lot-gallery__item"><img data-srcset="/front.jpg?w=320 320w, /front.jpg?w=1440 1440w"></div>
          <div class="lot-gallery__item"><img src="/floorplan.jpg"></div>
        </div>
        <div class="lot-summary__description">{summary}</div>
        <footer>Other lots: Sold Prior, Withdrawn. General fees inclusive of VAT.</footer>
        </html>''','html.parser')


URL='https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/123456/'


class BarnardMarcusClassificationTests(unittest.TestCase):
    def test_advertised_latest_results_are_discovered_without_archive_expansion(self):
        html=BeautifulSoup('''<a href="/auctions/17-november-2026/">Next</a>
          <a href="/auctions/15-october-2026/?lots=2">Available lots</a>
          <a href="/auctions/10-september-2026/">Older</a>
          <a href="https://example.com/auctions/16-october-2026/">External</a>''','html.parser')
        with patch('collectors.barnard_marcus.soup', return_value=html), patch('collectors.barnard_marcus.date') as clock:
            clock.today.return_value=date(2026,10,17)
            self.assertEqual(_advertised_dates(),{'2026-11-17','2026-10-15'})

    def test_discovery_normalises_first_party_urls_and_excludes_unadvertised_history(self):
        recent=URL
        future=URL.replace('15-october','17-november')
        old=URL.replace('15-october','10-september')
        with patch('collectors.barnard_marcus._advertised_dates',return_value={'2026-10-15','2026-11-17'}), \
             patch('collectors.barnard_marcus._sitemap_urls',return_value={recent,recent+'?tracking=1',future,old,recent.replace('www.barnardmarcusauctions.co.uk','example.com'),recent+'extra'}):
            urls,scope=_discover()
        self.assertEqual(urls,{recent,future})
        self.assertEqual(scope,{'2026-10-15','2026-11-17'})

    def test_current_let_car_park_with_residential_planning_is_retained_as_withdrawn(self):
        lot=_parse_detail(page('Parcel of land measuring circa 1/3 acre. B8 usage. '
            'Tenancy Details: The land is currently let for cruise car parking at £38,000 PA. '
            'Additional planning permission for residential development comprising 9 apartments.',
            'Withdrawn prior to auction £375,000'),URL)
        self.assertEqual(lot.status,'WITHDRAWN')
        self.assertEqual(lot.annual_rent,38000)
        self.assertAlmostEqual(lot.site_area_acres,1/3)
        self.assertIsNone(publication_exclusion(lot.to_dict()))
        self.assertIsNone(_parse_detail(page('Two bedroom flat with residents car parking. '
            'Potential for commercial parking subject to planning.'),URL))

    def test_missing_discovery_is_not_a_healthy_empty_catalogue(self):
        with patch('collectors.barnard_marcus._discover',return_value=(set(),{'2026-10-15'})):
            result=collect()
        self.assertEqual(result.status,'FAILED')
        self.assertEqual(result.discovered_count,0)

    def test_availability_requires_complete_distinct_first_party_pages(self):
        options={'endpointUrl':'/umbraco/Api/SearchApi/Search?auctionHouseId=1&auctionId=2',
                 'filters':[{'name':'lots','options':[{'label':'show all','value':'1','isDefault':True},
                                                    {'label':'available','value':'2','isDefault':False}]}]}
        html=BeautifulSoup('<div></div>','html.parser')
        html.div['data-dc-lots-search-options']=json.dumps(options)
        def payload(number,url,total=2):
            return {'pagination':{'totalCount':total,'pageCount':2,'currentPage':number},
                    'items':[{'url':url,'statusName':'Available'}]}
        second=URL.replace('123456','654321')
        for pages,valid in [([payload(1,URL),payload(2,second)],True),
                            ([payload(1,URL),payload(2,URL)],False),
                            ([payload(1,URL),payload(2,second,3)],False),
                            ([payload(1,URL),payload(2,second.replace('www.barnardmarcusauctions.co.uk','example.com'))],False)]:
            client=MagicMock()
            client.__enter__.return_value=client
            client.get.side_effect=[MagicMock(json=MagicMock(return_value=p)) for p in pages]
            with patch('collectors.barnard_marcus.soup',return_value=html), \
                 patch('collectors.barnard_marcus.requests.Session',return_value=client):
                if valid:
                    self.assertEqual(_available_urls('2026-10-15'),({URL,second},{'reported_rows':2,'observed_rows':2,'complete':True}))
                    self.assertEqual(client.get.call_args_list[0].kwargs['params'],{'lots':'2','page':1})
                else:
                    with self.assertRaises(ValueError):_available_urls('2026-10-15')

    def test_source_failure_does_not_invent_availability_from_guide_price(self):
        for available,terminal in [(True,False),(False,False),(True,True)]:
            lot=_parse_detail(page('Freehold ground floor shop investment.',
                'Withdrawn prior' if terminal else 'Guide price £100,000'),URL)
            with patch('collectors.barnard_marcus._discover',return_value=({URL},{'2026-10-15'})), \
                 patch('collectors.barnard_marcus._hydrate',return_value=lot), \
                 patch('collectors.barnard_marcus._available_urls',**({'return_value':({URL},{'complete':True})} if available else {'side_effect':ValueError('feed failed')})):
                result=collect()
            self.assertEqual(verified_post_auction_available(result.lots[0].to_dict()),available and not terminal)
            if not available:self.assertEqual(result.status,'DEGRADED')

    def test_partial_source_count_preserves_positive_evidence_but_stays_degraded(self):
        lot=_parse_detail(page('Freehold ground floor shop investment.'),URL)
        coverage={'reported_rows':2,'observed_rows':1,'complete':False}
        with patch('collectors.barnard_marcus._discover',return_value=({URL},{'2026-10-15'})), \
             patch('collectors.barnard_marcus._hydrate',return_value=lot), \
             patch('collectors.barnard_marcus._available_urls',return_value=({URL},coverage)):
            result=collect()
        self.assertEqual(result.status,'DEGRADED')
        self.assertEqual(result.reconciliation['availability_coverage']['2026-10-15'],coverage)
        self.assertTrue(verified_post_auction_available(result.lots[0].to_dict()))

    def test_scoped_particulars_retain_range_income_and_first_gallery_image(self):
        lot=_parse_detail(page('Freehold mixed-use building. Location: Close to a railway station. '
            'Description: Ground floor shop and flat above. Tenancy: Shop let to Example Ltd for a term of 10 years '
            'from 1 January 2023. Rent reserved: £12,000 per annum. EPC Rating: C. '
            'Important Notice: A fee of £1,800 inclusive of VAT is payable.'),URL)
        self.assertEqual((lot.guide_price,lot.guide_price_upper),(70000,80000))
        self.assertEqual(lot.annual_rent,12000)
        self.assertEqual(lot.lease_term,'10 years')
        self.assertEqual(lot.lease_start,'1 January 2023')
        self.assertEqual(lot.epc,'C')
        self.assertEqual(lot.status,'CURRENT')
        self.assertEqual(lot.vat_status,'UNKNOWN')
        self.assertTrue(lot.image_is_primary)
        self.assertEqual(lot.image_url,'https://www.barnardmarcusauctions.co.uk/front.jpg?w=1440')
        self.assertIn('Freehold mixed-use',lot.description)
        self.assertNotIn('railway station',lot.description)

    def test_terminal_commercial_lots_are_retained_with_their_own_status(self):
        for label in ['Sold Prior','Withdrawn','Postponed']:
            with self.subTest(label=label):
                lot=_parse_detail(page('Freehold ground floor shop. Vacant possession.',label),URL)
                self.assertEqual(lot.status,label.upper())
                self.assertIsNone(lot.annual_rent)

    def test_current_october_102_flat_is_not_classified_from_neighbourhood_shops(self):
        self.assertIsNone(_parse_detail(page('Leasehold second floor flat. 38 years remaining on the lease. '
            'Location: Near shops, bars and restaurants. Accommodation: Two bedrooms, reception room, kitchen, bathroom/wc. '
            'Lease: 99 years from 25/12/1965. Important Notice: Fees apply.'),URL))

    def test_missing_particulars_is_a_fetch_failure_not_a_noncommercial_lot(self):
        with self.assertRaisesRegex(ValueError,'particulars'):
            _parse_detail(BeautifulSoup('<h1>Temporary page</h1>','html.parser'),URL)

    def test_residential_flat_is_not_rescued_by_location_restaurants(self):
        text = (
            "Long leasehold second floor flat. "
            "Location: Shopping amenities are available locally with a further range of shops, "
            "bars and restaurants found within Notting Hill."
        )
        self.assertFalse(_is_target_particulars(text))

    def test_mixed_use_shop_and_flats_is_included(self):
        text = (
            "Freehold mixed-use building with ground floor shop. "
            "Upper residential parts sold off on a lease. Investment (Rent reserved: £36,000 per annum). "
            "Location: The property occupies a prominent trading position."
        )
        self.assertTrue(_is_target_particulars(text))

    def test_sale_summary_stops_before_location_chrome(self):
        text = "Freehold three-storey mixed-use building. Location: shops bars restaurants retail parade."
        self.assertNotIn("restaurants", _sale_summary(text).lower())


if __name__ == "__main__":
    unittest.main()
