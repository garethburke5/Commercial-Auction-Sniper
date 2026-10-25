from scripts import harvest_dawsons_history as d


def page(description, price="£110,000", next_page="", slug="25-new-dock-road"):
    return f'''<h4>1 Past Auction Properties</h4>
    <div class="photo"><div class="homes-tag">Sold</div></div>
    <div class="homes-content"><a href="auction/{slug}"><h3>25 New Dock Road, Llanelli, SA15 2EG</h3></a>
    <div class="price-properties">{price}</div><ul class="homes-list"><li>Terrace</li></ul></div>
    <div class="modal" id="{slug}"><p>{description}</p>
    <div class="homes-content"><ul><li>3 Bedrooms</li></ul></div></div>
    <a href="#carousel">Next</a>{next_page}'''


def test_sold_does_not_promote_unlabelled_advertised_price_to_sale_price():
    rows, count, next_url = d.parse_page(page("WILL CLOSE ON THE 29TH JULY 2026 AT 4PM."), d.INDEX, {"sha256": "one"})
    assert count == 1 and len(rows) == 1 and next_url is None
    row = rows[0]
    assert row["auction_date"] == "2026-07-29"
    assert row["status"] == "sold"
    assert row["source_display_price"] == 110000
    assert row["sale_price"] is None and row["guide_price"] is None
    assert row["postcode"] == "SA15 2EG"
    assert row["source_evidence"] == [{"sha256": "one"}]


def test_explicit_financial_labels_and_scoped_pagination():
    rows, _, next_url = d.parse_page(page("No auction date", "Guide price £110,000", '<a href="/past-auctions.php?page=2">Next</a>'), d.INDEX, {})
    assert rows[0]["guide_price"] == 110000 and rows[0]["sale_price"] is None
    assert rows[0]["auction_date"] is None
    assert next_url == d.INDEX + "?page=2"
    _, _, third_page = d.parse_page(page("No date", next_page='<a href="/past-auctions.php?page=3">Next</a>'), d.INDEX + "?page=2", {})
    assert third_page == d.INDEX + "?page=3"
    sold, _, _ = d.parse_page(page("No date", "Sold for £120,000"), d.INDEX, {})
    assert sold[0]["sale_price"] == 120000 and sold[0]["guide_price"] is None


def test_dates_are_never_borrowed_from_page_footer_or_other_properties():
    html = page("WILL CLOSE ON THE 24TH OF JUNE AT 2PM.") + '<footer>AUCTION 24TH JUNE 2026</footer>'
    rows, _, _ = d.parse_page(html, d.INDEX, {})
    assert rows[0]["auction_date"] is None
    assert d.dated("WILL CLOSE ON THE 24TH OF JUNE 2026 AT 2PM")[0] == "2026-06-24"
    assert d.dated("WILL CLOSE ON THE 24TH JUNE 2026. WILL CLOSE ON THE 25TH JUNE 2026.")[0] is None


def test_repeat_auction_dates_keep_separate_appearances():
    first, _, _ = d.parse_page(page("AUCTION 12TH MAY 2025"), d.INDEX, {})
    second, _, _ = d.parse_page(page("AUCTION 12TH MAY 2026"), d.INDEX, {})
    assert first[0]["appearance_id"] != second[0]["appearance_id"]


def test_failed_later_page_preserves_first_page_and_does_not_claim_completion(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(d.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(d.corpus, "DATA", tmp_path / "data/auction_history")
    html = page("AUCTION 12TH MAY 2025", next_page='<a href="/past-auctions.php?page=2">Next</a>').replace('1 Past', '2 Past')
    class Response:
        content = html.encode()
        text = html
        url = d.INDEX
        def raise_for_status(self): pass
    def get(url, **kwargs):
        if "page=2" in url:
            raise requests.Timeout("source unavailable")
        return Response()
    monkeypatch.setattr(d.requests, "get", get)
    first = d.harvest()
    assert first["run_new_appearances"] == 1
    assert first["archive_pagination_complete"] is False and first["failures"]
    second = d.harvest()
    assert second["run_new_appearances"] == 0
    assert second["property_appearances_captured"] == 1


def test_completed_archive_is_idempotent_and_uses_daily_refresh(tmp_path, monkeypatch):
    monkeypatch.setattr(d.corpus, "ROOT", tmp_path)
    monkeypatch.setattr(d.corpus, "DATA", tmp_path / "data/auction_history")
    html = page("AUCTION 12TH MAY 2025")
    class Response:
        content = html.encode()
        text = html
        url = d.INDEX
        def raise_for_status(self): pass
    calls = []
    def get(url, **kwargs): calls.append(url); return Response()
    monkeypatch.setattr(d.requests, "get", get)
    assert d.harvest()["archive_pagination_complete"]
    d.harvest()
    assert len(calls) == 1
    assert d.harvest(refresh=True)["run_new_appearances"] == 0
