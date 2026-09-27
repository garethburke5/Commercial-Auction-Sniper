from unittest.mock import patch
from bs4 import BeautifulSoup
from collectors import auction_house_regions_resilient as collector
from collectors.auction_house_regions import _fallback_catalogue_lot
from collectors.core import Lot


def test_card_fallback_does_not_certify_detail_capture_or_authoritative_pruning():
    page=BeautifulSoup('<article><a href="https://wales.auctionhouse.co.uk/lot/redirect/123">'
                       'Lot 1 *Guide £98,000 Commercial Property 67 High Street, Rhymney NP22 5LP'
                       '</a></article>','lxml')
    with patch.object(collector.base,'_future_events',return_value={'https://example.test/event':'2099-10-07'}), \
         patch.object(collector.base,'_fetch',return_value=page), \
         patch.object(collector.base,'_direct_first_party_lot',return_value=None), \
         patch.object(collector,'detail_lot',return_value=None):
        result=collector._collect_region('wales')
    assert len(result.lots)==1
    assert result.status=='DEGRADED' and not result.authoritative_snapshot
    assert result.reconciliation['detail_pages_inspected']==0
    assert result.reconciliation['detail_failures']==1
    assert result.reconciliation['catalogue_fallbacks']==1


def test_outage_redirect_retains_same_sale_particulars_without_claiming_new_capture():
    old=Lot('Auction House Wales','https://wales.auctionhouse.co.uk/lot/details/uuid',
            '67 High Street, Rhymney NP22 5LP',auction_date='2026-10-07',guide_price=98000,
            tenure='Freehold',description='Vacant ground floor solicitors office and first floor apartment. '
            'Commercial accommodation extends to 250 sq m.',property_type='Mixed Use',occupation='Vacant',
            collected_at='2026-09-26T22:17:41+00:00').to_dict()
    fallback=_fallback_catalogue_lot(old['source'],'https://wales.auctionhouse.co.uk/lot/redirect/123',
              'Guide £95,000 Commercial Property',old['address'],None,'2026-10-07')
    restored,used=collector._restore_fallback_details(fallback,[old])
    assert used and restored.url==old['url'] and restored.description==old['description']
    assert restored.tenure=='Freehold' and restored.property_type=='Mixed Use'
    assert restored.guide_price==95000 and restored.collected_at==old['collected_at']
    fallback.auction_date='2026-11-11'
    assert not collector._restore_fallback_details(fallback,[old])[1]
