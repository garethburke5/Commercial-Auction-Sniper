from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import harvest_harman_healy_results as hh


FIXTURE = """
<html><body>
<div>Showing results 1 - 2 of 2</div>
<div class="lot-panel"><div class="panel-title">Online: Lot 7A | Auction Ended -
<time datetime="2023-05-18T11:05:00.0000000+00:00">18/05/2023 11:05</time></div>
<a href="/lot/details/381c1785-8681-4361-9653-9211dc113afd"><img class="list-image" src="/one.jpg"></a>
<div class="list-info"><h3 class="list-address">1 High Street, London, SW1A 1AA</h3>
<h4 class="lot-data-heading">Shop and upper parts</h4><p>A mixed-use investment.</p></div>
<div class="list-guideprice">Result: <strong>Sold for £275,000</strong></div></div>
<div class="lot-panel"><div class="panel-title">Online: Lot 8 | Auction Ended -
<time datetime="2023-05-18T11:10:00.0000000+00:00">18/05/2023 11:10</time></div>
<a href="/lot/details/28894983-a5cd-45cf-a760-772f3d14065d"></a>
<div class="list-info"><h3 class="list-address">Flat 2, 9 Road, Leeds, LS1 1AA</h3>
<h4 class="lot-data-heading">One bedroom flat</h4><p>A leasehold flat.</p></div>
<div class="list-guideprice">Result: <strong>No Bids</strong></div></div>
</body></html>
"""


def test_denominator_and_rows_preserve_all_property_types():
    assert hh.published_total(FIXTURE) == 2
    rows = hh.parse_page(FIXTURE, 1, {"source_url": hh.ARCHIVE_URL})
    assert len(rows) == 2
    assert rows[0]["lot_number"] == "7A"
    assert rows[0]["auction_date"] == "2023-05-18"
    assert rows[0]["status"] == "sold"
    assert rows[0]["sale_price"] == 275000
    assert rows[0]["sector"] == "mixed-use"
    assert rows[1]["status"] == "unsold"
    assert rows[1]["sector"] == "residential"
    assert all(row["record_quality"] == "address_record" for row in rows)


def test_stable_identity_is_source_lot_id_not_address():
    rows = hh.parse_page(FIXTURE, 1, {})
    assert rows[0]["appearance_id"] == "Harman Healy|eig-lot:381c1785-8681-4361-9653-9211dc113afd"
    assert rows[0]["source_auction_id"] == "harman-healy:2023-05-18"


def test_unsold_asking_amount_is_not_a_sale():
    assert hh.status_and_price('Unsold £175,000')==('unsold',None)


def test_explicit_sale_price_without_sold_word_is_achieved_price():
    assert hh.status_and_price('Sale price: £332,500 41 bids') == ('sold', 332500)


def test_sale_agreed_prior_outcome_is_preserved():
    assert hh.status_and_price('Result: Sale Agreed Prior') == ('sold_prior', None)


def test_configure_supports_retained_search_grids():
    original = (hh.BASE, hh.ARCHIVE_URL, hh.AUCTIONEER, hh.SLUG, hh.OPERATOR_METADATA)
    try:
        hh.configure(
            "https://purplebricks.gotoproperties.co.uk/",
            "Purplebricks Online Auctions",
            "purplebricks-online-auctions",
            archive_path="/search",
            operator_metadata={"operator_legal_name": "Genle Limited"},
        )
        assert hh.ARCHIVE_URL == "https://purplebricks.gotoproperties.co.uk/search"
        assert "lotResultType=All" in hh.archive_page_url(1)
        assert hh.OPERATOR_METADATA == {"operator_legal_name": "Genle Limited"}
    finally:
        hh.BASE, hh.ARCHIVE_URL, hh.AUCTIONEER, hh.SLUG, hh.OPERATOR_METADATA = original


def test_committed_offer_cards_are_reconciled_but_not_admitted():
    fixture = """
    <html><body><div>Showing results 1 - 1 of 1</div>
    <div class="lot-panel"><h3 class="panel-title">Committed Offers Invited</h3>
    <a href="/lot/details/offer-only"><img class="list-image" src="/one.jpg"></a>
    <div class="list-info"><h3 class="list-address">1 Offer Road, London, E1 1AA</h3></div>
    <div class="list-guideprice">Offers in Excess of: £225,000</div></div>
    </body></html>
    """
    assert hh.parse_page(fixture, 1, {}) == []
    exclusions = hh.non_auction_offer_cards(fixture, 1)
    assert exclusions == [{
        "reason": "committed_offer_not_an_auction_appearance",
        "address": "1 Offer Road, London, E1 1AA",
        "source_url": "https://harman-healy.co.uk/lot/details/offer-only",
        "source_position": 1,
    }]


def test_global_eig_identity_overlap_is_detected_without_address_merging(monkeypatch, tmp_path):
    monkeypatch.setattr(hh.corpus, 'DATA', tmp_path / 'data/auction_history')
    hh.corpus.write_rows('other-platform/canonical', [{
        'appearance_id': 'Other|eig-lot:shared-id',
        'auctioneer': 'Other EIG White Label',
        'auction_date': '2024-02-01',
        'source_lot_id': 'shared-id',
        'property_id': 'shared-id',
        'identity_method': 'first_party_published_eig_lot_id',
        'original_url': 'https://other.example/lot/details/shared-id',
    }])
    overlaps = hh.global_eig_source_ids('purplebricks-online-auctions')
    assert overlaps['shared-id'] == [{
        'appearance_id': 'Other|eig-lot:shared-id',
        'auctioneer': 'Other EIG White Label',
        'auction_date': '2024-02-01',
        'original_url': 'https://other.example/lot/details/shared-id',
    }]


def test_growing_archive_refetches_old_pages_before_reconciliation(monkeypatch,tmp_path):
    import json
    monkeypatch.setattr(hh.corpus,'ROOT',tmp_path)
    monkeypatch.setattr(hh.corpus,'DATA',tmp_path/'data/auction_history')
    monkeypatch.setattr(hh,'PAGE_SIZE',2)
    saved=[]
    for page in range(1,4):
        evidence={'page':page,'source_url':f'https://example.com/{page}','snapshot_path':f'page{page}.json.gz'}
        hh.corpus.save_gzip(tmp_path/evidence['snapshot_path'],{'html':f'{page}:6','evidence':evidence})
        saved.append(evidence)
    hh.corpus.save_json(hh.corpus.DATA/'auctions/harman-healy/retained-past-auctions.json',{'catalogue_complete':True,'published_lots_offered':6,'source_evidence':saved})
    fetched=[]
    def fetch(page):
        fetched.append(page)
        return page,f'{page}:8'.encode(),f'https://example.com/{page}'
    monkeypatch.setattr(hh,'fetch',fetch)
    monkeypatch.setattr(hh,'published_total',lambda html:int(html.split(':')[1]))
    monkeypatch.setattr(hh,'parse_page',lambda html,page,ev:[{'appearance_id':f'row:{page}:{i}','source_lot_id':f'{page}-{i}','auction_date':'2026-10-01','address':f'{page}-{i} High Street','source_evidence':ev} for i in range(2)])
    hh.harvest()
    assert sorted(fetched)==[1,2,3,4]
    state=json.loads((hh.corpus.DATA/'auctions/harman-healy/retained-past-auctions.json').read_text())
    assert state['catalogue_complete'] is True and state['lots_captured']==8
