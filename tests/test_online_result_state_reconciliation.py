from scripts.reconcile_online_result_state_errors import reclassify_state


LIMITATION = (
    "Rows are individual online lot endings; "
    "original catalogue denominators are not published"
)


def test_denominator_limitation_is_not_a_fetch_failure(monkeypatch):
    monkeypatch.setattr(
        "scripts.reconcile_online_result_state_errors.corpus.now",
        lambda: "2026-10-25T18:30:00Z",
    )
    state = {
        "catalogue_complete": False,
        "archive_pagination_complete": True,
        "lots_captured": 12,
        "completion_scope": "retained rows",
        "errors": [{"error": LIMITATION}],
    }
    updated = reclassify_state(state, LIMITATION)
    assert updated["catalogue_complete"] is False
    assert updated["source_rows_complete"] is True
    assert updated["denominator_reconciled"] is False
    assert updated["errors"] == []
    assert updated["reconciliation_note"] == {
        "kind": "original_event_denominator_unavailable",
        "retained_scope": "retained rows",
        "retained_rows": 12,
    }


def test_real_fetch_errors_are_preserved():
    fetch_error = {"page": 3, "error": "TimeoutError: timed out"}
    state = {
        "archive_pagination_complete": False,
        "lots_captured": 8,
        "completion_scope": "retained rows",
        "errors": [{"error": LIMITATION}, fetch_error],
    }
    updated = reclassify_state(state, LIMITATION)
    assert updated["source_rows_complete"] is False
    assert updated["errors"] == [fetch_error]
