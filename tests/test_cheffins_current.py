from datetime import date
from bs4 import BeautifulSoup
from collectors.cheffins_current import SEARCH, collect_cheffins, detail, lot_url
from collectors.publication_quality import commercial_decision


def page(html): return BeautifulSoup(html,'lxml')
def card(n, day='19/11/2026', status='End Time'):
    return f'''<div class="list-panel"><h3>Online: {status} - {day} 14:00</h3>
    <a href="https://auctions.thecpn.co.uk/lot/details/abcd-{n}">1 High Street</a>
    <p>Guide Price*: £225,000 Minimum Opening Bid: £195,000</p></div>'''
DETAIL='''<h1>1 High Street, Walsall WS1 1QD</h1>
<img alt="Lot Image" src="https://example.test/primary.jpg">
<h3 class="lot-details-heading">Description</h3><p>Freehold warehouse with office accommodation, vacant possession. A large loading bay.</p>
<h3 class="lot-details-heading">Location</h3><p>Town centre, near local shops.</p>
<h3 class="lot-details-heading">Tenure</h3><p>Freehold with vacant possession</p>
<h3 class="lot-details-heading">VAT</h3><p>No VAT is payable on the purchase price.</p>
<h3 class="lot-details-heading">Outgoings</h3><p>Rates payable £20,952 per annum.</p>
<h3 class="lot-details-heading">Auctioneer's Note</h3><p>Buyer fee £2,100 including VAT.</p>
<h3 class="lot-details-heading">Accommodation</h3><div class="table-responsive"><table><tr><td>Total Floor Area</td><td>4,176</td><td>387.95</td></tr></table></div>
<h5>Vendors solicitor</h5><p>Private contact details</p>
<div>Withdrawn Postponed Sold Prior — bidding help</div>'''


def test_detail_retains_guide_area_vat_and_no_false_income_or_status():
    row=detail('https://auctions.thecpn.co.uk/lot/details/abcd-1',
               {'text':'Guide Price £225,000 Minimum Opening Bid £195,000','day':'2026-11-19'},page(DETAIL))
    assert row.guide_price==225000 and row.annual_rent is None
    assert row.area_sqft==4176 and row.area_sqm==387.95
    assert row.vat_status=='NOT APPLICABLE' and row.status=='CURRENT'
    assert row.image_url.endswith('primary.jpg')
    assert 'Private contact' not in row.description and 'Buyer fee' not in row.description


def test_pagination_counts_past_separately_and_deduplicates_shared_links():
    pages={SEARCH:page('Showing results 1 - 1 of 2'+card(1)+
           '<ul class="pagination"><a href="/search?page=2">2</a></ul>'),
           SEARCH+'?page=2':page('Showing results 2 - 2 of 2'+card(1)+card(2,'01/01/2020','Auction Ended'))}
    def fetch(url):return pages[url] if url in pages else page(DETAIL)
    result=collect_cheffins(fetch,date(2026,10,17))
    assert result.status=='LIVE' and len(result.lots)==1
    assert not result.authoritative_snapshot  # Timed results cannot retire rostrum inventory.
    assert result.reconciliation['catalogue_total_lots']==2
    assert result.reconciliation['source_lot_count']==1
    assert result.reconciliation['past_auction_exclusions']==1
    assert result.lots[0].source=='Cheffins'


def test_denominator_gap_or_detail_failure_cannot_certify_empty_catalogue():
    for html in ['Showing results 1 - 2 of 2'+card(1),'<h1>Search unavailable</h1>']:
        result=collect_cheffins(lambda u:page(html if u==SEARCH else DETAIL),date(2026,10,17))
        assert result.status=='DEGRADED' and not result.authoritative_snapshot
    def fail(url):
        if url==SEARCH:return page('Showing results 1 - 1 of 1'+card(1))
        raise RuntimeError('unavailable')
    result=collect_cheffins(fail,date(2026,10,17))
    assert result.status=='DEGRADED' and not result.lots


def test_residential_and_unknown_assets_excluded_and_withdrawn_retained():
    def fetch(url):
        if url==SEARCH:return page('Showing results 1 - 2 of 2'+card(1,'01/01/2020','Withdrawn Auction Ended')+card(2))
        if url.endswith('-1'):return page(DETAIL)
        return page(DETAIL.replace('Freehold warehouse with office accommodation, vacant possession. A large loading bay.',
            'A detached three-bedroom house with a study, near the local social club.'))
    result=collect_cheffins(fetch,date(2026,10,17))
    assert len(result.lots)==1 and result.lots[0].status=='WITHDRAWN'
    assert result.reconciliation['classification_rejections']==1
    assert commercial_decision({'description':'Function room, bar and kitchen. Business rates: Club and premises assessment.'}) is True
    assert lot_url('https://untrusted.test/lot/details/abcd-1') is None
