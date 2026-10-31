import json
from bs4 import BeautifulSoup
from web_platform.archive_status import apply_archive_status
from web_platform.catalogue import Catalogue
from web_platform.site import Site

URL='http://auctions.savills.co.uk/auctions/20--21-october-2026-244/3-queen-street-haverhill-cb9-9dz-25498'


def test_exact_appearance_correction_does_not_change_relisting_or_neighbour():
    original={'url':URL,'auction_date':'2026-10-21','status':'ARCHIVED'}
    apply_archive_status(original,in_current_catalogue=False)
    assert original['auction_outcome']=='Withdrawn'
    assert original['status']=='ARCHIVED'  # Still excluded from current searches.
    for other in (dict(url=URL,auction_date='2099-10-21'),
                  dict(url=URL.replace('25498','25499'),auction_date='2026-10-21')):
        apply_archive_status(other)
        assert not other.get('auction_outcome')
        assert not other['archive_notice']


def test_archive_pages_snapshot_metadata_and_active_search(tmp_path):
    archived={'source':'Savills Auctions','url':URL,'address':'3 Queen Street, Haverhill, CB9 9DZ',
        'auction_date':'2026-10-21','status':'ARCHIVED','guide_price':145000,'annual_rent':18000,
        'lot_number':'303','tenure':'Freehold','description':'A mixed use property comprising a shop and flat. '*8}
    current=dict(archived,address='8 Example Street, AB1 2CD',url='https://example.org/lot/8',auction_date='2099-10-21',status='CURRENT')
    (tmp_path/'data/auction_history').mkdir(parents=True)
    (tmp_path/'data/properties.json').write_text(json.dumps({'properties':[current],'archive':[archived],'generated_at':'2026-10-31'}))
    (tmp_path/'data/auction_history/progress.json').write_text(json.dumps({'individual_lot_records_captured':1,'by_sector':{'commercial':0,'mixed-use':1}}))
    catalogue=Catalogue(tmp_path);site=Site(catalogue,'https://example.org')
    row=next(r for r in catalogue.all_properties if r['url']==URL)
    assert row not in catalogue.properties
    assert row['id']=='9a273d18920970f1f3c9'
    pages=dict(site.routes())
    for path in (row['path'],row['snapshot_path']):
        soup=BeautifulSoup(pages[path],'html.parser')
        assert 'withdrawn from the October 2026 auction' in soup.select_one('.archive-notice').text
        assert 'Current availability is not confirmed' in soup.select_one('.archive-notice').text
        assert 'Historical guide price' in soup.text
        assert '£145,000' in soup.text
        assert 'Archived' in soup.title.text
        assert 'archiv' in soup.select_one('meta[name=description]')['content'].lower()
        assert 'withdrawn' in soup.select_one('meta[property="og:description"]')['content']
    house=BeautifulSoup(pages['/auctioneers/savills-auctions/'],'html.parser')
    card=house.select_one('[data-id="9a273d18920970f1f3c9"]')
    assert 'withdrawn from the October 2026 auction' in card.select_one('.archive-label').text
    assert 'Historical guide price' in card.text
    live=BeautifulSoup(pages[catalogue.properties[0]['path']],'html.parser')
    assert not live.select_one('.archive-notice')


def test_unknown_archived_outcome_is_not_invented():
    row={'status':'ARCHIVED','url':'https://example.org/unknown','auction_date':'2020-01-01'}
    apply_archive_status(row,in_current_catalogue=False)
    assert row['archive_notice']['title']=='Archived auction listing'
    assert not row.get('auction_outcome')
