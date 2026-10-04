import pytest

from scripts.harvest_future_property_auctions import (
    epoch_date,
    manifest_rows,
    parse_auction,
    sanitized_snapshot,
    fetch_manifest,
)


UUID = "auction-uuid"
LISTING = "listing-uuid"
PAYLOAD = {
    "information": {
        "auction": {"uuid": UUID, "endsAt": 1790863200000},
        "listings": {LISTING: {
            "uuid": LISTING, "id": 42, "auctionUuid": UUID, "lotNumber": "7",
            "title": "10&nbsp;High Street, Glasgow G1 1AA",
            "description": '<p>Retail investment</p><a href="property_details.asp?id=14500001">details</a>',
            "summary": "Tenanted&nbsp;Freehold&nbsp;Commercial",
            "images": ["image-uuid"],
        }},
    },
    "sellingInformation": {
        "sales": {LISTING: {"totalBids": 4, "reserve": 100000}},
        "saleStatuses": {LISTING: {
            "listingUuid": LISTING, "complete": True, "sold": True,
            "withdrawn": False, "suspended": False, "endsAt": 1790863200000,
            "highestBidUuid": "bid-uuid",
        }},
        "bids": {"bid-uuid": {
            "uuid": "bid-uuid", "listingUuid": LISTING, "amount": 125000,
            "placedAt": 1790863100000, "userUuid": "must-not-survive", "cancelled": False,
        }},
    },
    "attachments": {"image-uuid": {
        "uuid": "image-uuid", "basePath": "https://media.test/image/upload/",
        "versionAndPublicId": "v1/folder/image.jpg",
    }},
    "registrants": {"must-not-survive": {"name": "private"}},
}
MANIFEST = {
    "auction_uuid": UUID, "auction_id": "123", "title": "1 October 2026",
    "auction_end_time": 1790863200000, "auction_date": "2026-10-01",
}


def test_manifest_requires_stable_distinct_auction_identities():
    rows = manifest_rows({"basicAuctionBidJSModelList": [{
        "auctionUuid": UUID, "auctionId": 123, "auctionTitle": "Auction",
        "auctionEndTime": 1790863200000,
    }]})
    assert rows[0]["auction_date"] == "2026-10-01"
    with pytest.raises(ValueError, match="duplicate"):
        manifest_rows({"basicAuctionBidJSModelList": [
            {"auctionUuid": UUID, "auctionId": 1}, {"auctionUuid": UUID, "auctionId": 2},
        ]})


def test_complete_payload_banks_address_outcome_price_and_provenance():
    rows, state = parse_auction(PAYLOAD, MANIFEST, {"sha256": "abc", "source_url": "api"})
    assert len(rows) == 1 and state["catalogue_complete"] is True
    row = rows[0]
    assert row["address"] == "10 High Street, Glasgow G1 1AA"
    assert row["postcode"] == "G1 1AA"
    assert row["sale_price"] == 125000 and row["status"] == "sold"
    assert row["property_id"] == "14500001"
    assert row["image_urls"] == ["https://media.test/image/upload/v1/folder/image.jpg"]
    assert row["appearance_id"].endswith("listing:listing-uuid")


def test_snapshot_strips_people_bid_histories_and_hidden_reserve():
    snapshot = sanitized_snapshot(PAYLOAD, {"sha256": "abc"})
    text = str(snapshot)
    assert "must-not-survive" not in text
    assert "reserve" not in snapshot["public_sales"][LISTING]
    assert 100000 not in snapshot["public_sales"][LISTING].values()
    assert snapshot["public_sales"][LISTING]["highestBid"]["amount"] == 125000


def test_non_reconciling_payload_is_rejected():
    broken = {**PAYLOAD, "sellingInformation": {**PAYLOAD["sellingInformation"], "sales": {}}}
    with pytest.raises(ValueError, match="do not reconcile"):
        parse_auction(broken, MANIFEST, {})


def test_epoch_date_is_utc_and_null_safe():
    assert epoch_date(1790863200000) == "2026-10-01"
    assert epoch_date(None) is None


def test_manifest_refresh_can_reuse_saved_first_party_snapshot(monkeypatch, tmp_path):
    import scripts.harvest_future_property_auctions as future

    snapshot = tmp_path / "sources/future_property_auctions/archive-saved.json.gz"
    snapshot.parent.mkdir(parents=True)
    saved_payload = {"basicAuctionBidJSModelList": [{
        "auctionUuid": UUID, "auctionId": 123, "auctionTitle": "Auction",
        "auctionEndTime": 1790863200000,
    }]}
    future.corpus.save_gzip(snapshot, {
        "evidence": {"retrieved_at": "2026-10-01T00:00:00+00:00", "snapshot_path": "saved"},
        "payload": saved_payload,
    })
    monkeypatch.setattr(future.corpus, "DATA", tmp_path)
    monkeypatch.setattr(future, "fetch_json", lambda _url: (_ for _ in ()).throw(
        future.requests.HTTPError("403 Client Error")
    ))

    payload, evidence, error = fetch_manifest()
    assert payload == saved_payload
    assert evidence["snapshot_path"] == "saved"
    assert "403 Client Error" in error


def test_fetch_json_retries_transient_source_responses(monkeypatch):
    import scripts.harvest_future_property_auctions as future

    statuses = iter((403, 503, 200))
    calls = []
    sleeps = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {"content-type": "application/json"}
            self.content = b'{"ok": true, "padding": 1}'

        def raise_for_status(self):
            if self.status_code >= 400:
                raise future.requests.HTTPError(f"{self.status_code} Client Error")

        def json(self):
            return {"ok": True, "padding": 1}

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(next(statuses))

    monkeypatch.setattr(future.requests, "get", get)
    monkeypatch.setattr(future.time, "sleep", sleeps.append)

    raw, payload = future.fetch_json("https://example.test/archive")

    assert payload["ok"] is True
    assert raw.startswith(b'{"ok": true')
    assert len(calls) == 3
    assert all(call[1]["headers"] == future.HEADERS for call in calls)
    assert sleeps == [2.0, 4.0]
