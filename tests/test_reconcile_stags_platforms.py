from scripts.reconcile_stags_platforms import find_matches


def row(identifier, date, address, description=""):
    return {"appearance_id": identifier, "auction_date": date, "address": address,
            "description": description}


def test_same_property_same_date_merges_but_reschedule_stays_distinct():
    bamboo = [row("b1", "2026-11-27", "Longmead, Lynton, EX35 6AA",
                  "Traditional auction of Longmead cottage garden paddock in Lynton Devon")]
    same = row("h1", "2026-11-27", "Longmead, Lynton",
               "Traditional auction of Longmead cottage garden paddock in Lynton Devon")
    stale = row("h2", "2026-10-28", "Longmead, Lynton",
                "Traditional auction of Longmead cottage garden paddock in Lynton Devon")
    matches = find_matches([same, stale], bamboo)
    assert [(source["appearance_id"], target["appearance_id"]) for source, target, _ in matches] == [("h1", "b1")]
