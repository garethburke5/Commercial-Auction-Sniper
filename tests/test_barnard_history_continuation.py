from datetime import date
from scripts.resume_barnard_marcus_history import discover

def test_discovery_uses_published_dates_and_deduplicates_detail_links():
    t='''<loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/731234</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/17-november-2026/</loc>
    <loc>https://example.com/auctions/01-january-2020/</loc>'''
    assert discover(t,date(2026,10,24))==[('2026-10-15','https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/')]

def test_legacy_reconciled_capture_does_not_restart_but_duplicates_do():
    from scripts.resume_barnard_marcus_history import reconciled
    s={'lot_enumeration_complete':True,'published_rows':2,'source_reported_rows':2,
       'lot_records':[{'source_record_id':'one'},{'source_record_id':'two'}]}
    assert reconciled(s)
    s['lot_records'][1]['source_record_id']='one'
    assert not reconciled(s)


def test_sitemap_xml_inventory_is_scoped_to_one_auction():
    from scripts.resume_barnard_marcus_history import sitemap_lot_urls_from_xml
    xml='''<loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/1/</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/2/</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/10-september-2026/3/</loc>'''
    assert sitemap_lot_urls_from_xml(
        'https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/',xml
    )==[
        'https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/1/',
        'https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/2/',
    ]
