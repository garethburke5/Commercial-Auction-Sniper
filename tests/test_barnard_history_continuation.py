from datetime import date
from scripts.resume_barnard_marcus_history import discover

def test_discovery_uses_published_dates_and_deduplicates_detail_links():
    t='''<loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/731234</loc>
    <loc>https://www.barnardmarcusauctions.co.uk/auctions/17-november-2026/</loc>
    <loc>https://example.com/auctions/01-january-2020/</loc>'''
    assert discover(t,date(2026,10,24))==[('2026-10-15','https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/')]
