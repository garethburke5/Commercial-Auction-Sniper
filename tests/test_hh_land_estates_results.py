from collections import Counter

from scripts.harvest_hh_land_estates_results import (
    COMPANY_NUMBER,
    EVENTS,
    OPERATOR,
    SOURCES,
    appearance,
    validate_event,
    validate_source_text,
)


def rows():
    return [row for event in EVENTS for row in event["lots"]]


def by_identity(identity):
    return next(row for row in rows() if row["identity"] == identity)


def test_reviewed_batch_has_individual_denominators_and_expected_metrics():
    values = rows()
    assert len(EVENTS) == 19
    assert len(values) == 55
    assert len({(event["date"], row["identity"]) for event in EVENTS for row in event["lots"]}) == 55
    assert Counter(row["sector"] for row in values) == {
        "land": 38,
        "mixed-use": 8,
        "commercial": 6,
        "residential": 3,
    }
    assert sum(row["guide_price"] is not None for row in values) == 32
    assert sum(row["sale_price"] is not None for row in values) == 28
    assert {event["date"][:4] for event in EVENTS} == {"2022", "2023", "2024", "2025"}


def test_related_interests_do_not_inherit_aggregate_prices():
    assert by_identity("hodge-hill-lot-1")["sale_price"] is None
    assert by_identity("hodge-hill-lot-2")["sale_price"] is None
    assert by_identity("hodge-hill-lot-3")["sale_price"] is None
    assert by_identity("hodge-hill-lots-1-3-combined")["sale_price"] == 930000

    assert by_identity("whitesmocks-lot-1")["sale_price"] is None
    assert by_identity("whitesmocks-lot-2")["sale_price"] is None
    assert by_identity("whitesmocks-whole")["sale_price"] == 200000

    for number in range(1, 5):
        assert by_identity(f"simgill-lot-{number}")["sale_price"] is None
    simgill = next(event for event in EVENTS if event["key"] == "2024-03-27-kendal")
    assert simgill["aggregate_result"] == {"simgill_lots_1_to_4": 278000}

    assert by_identity("mountain-view-lot-1")["sale_price"] is None
    assert by_identity("mountain-view-lot-2")["sale_price"] == 104000
    mountain = next(event for event in EVENTS if event["key"] == "2025-05-22-mountain-view")
    assert mountain["aggregate_result"] == 184000


def test_source_and_event_validation_require_reviewed_evidence():
    spec = SOURCES[0]
    text = " ".join(spec["required"])
    assert validate_source_text(text, spec) is True

    event = {
        "key": "example",
        "date": "2022-04-01",
        "sources": ("page",),
        "lots": ({"identity": "one", "evidence_phrase": "Bellow Hill"},),
    }
    assert validate_event(event, {"page": {"text": "Bellow Hill sold"}}) is True


def test_appearance_preserves_exact_date_prices_and_operator_identity():
    event = next(event for event in EVENTS if event["key"] == "2022-07-01-corfe-farm")
    value = event["lots"][0]
    captured = {
        "july-2022-review": {
            "source_url": "https://example.test/article",
            "retrieved_at": "2026-11-12T00:00:00+00:00",
            "sha256": "a" * 64,
            "snapshot_path": "data/example.gz",
            "basis": "test",
            "text": "corfe farm at wharton lancashire",
        }
    }
    row = appearance(event, value, captured)
    assert row["auction_date"] == "2022-07-01"
    assert row["auction_date_precision"] == "day"
    assert row["guide_price"] == 300000
    assert row["guide_price_high"] == 350000
    assert row["sale_price"] == 405000
    assert row["annual_rent"] is None
    assert row["operator_legal_name"] == OPERATOR
    assert row["operator_company_number"] == COMPANY_NUMBER


def test_operator_branches_and_trading_names_are_not_new_auctioneers():
    assert OPERATOR == "H&H LAND & ESTATES LIMITED"
    assert COMPANY_NUMBER == "03780434"
    assert {row["auctioneer"] for row in [
        appearance(
            next(event for event in EVENTS if event["key"] == "2022-07-01-corfe-farm"),
            by_identity("corfe-farm"),
            {
                "july-2022-review": {
                    "source_url": "https://example.test/article",
                    "retrieved_at": "2026-11-12T00:00:00+00:00",
                    "sha256": "b" * 64,
                    "snapshot_path": "data/example.gz",
                    "basis": "test",
                    "text": "corfe farm",
                }
            },
        )
    ]} == {"H&H Land & Estates"}
