from __future__ import annotations

import argparse

import savills_legacy_aid_capture_recovery as legacy

# Common Crawl's 2019 crawl IDs are stable published dataset identifiers.  Using
# the deterministic list keeps recovery working when the convenience
# collinfo.json endpoint is slow or unavailable.  These indexes remain discovery
# only: legacy.recover_candidate still requires a surviving first-party Savills
# page before anything is admitted to History V2.
CC_2019 = (
    "CC-MAIN-2019-51",
    "CC-MAIN-2019-47",
    "CC-MAIN-2019-43",
    "CC-MAIN-2019-39",
    "CC-MAIN-2019-35",
    "CC-MAIN-2019-30",
    "CC-MAIN-2019-26",
    "CC-MAIN-2019-22",
    "CC-MAIN-2019-18",
    "CC-MAIN-2019-13",
    "CC-MAIN-2019-09",
    "CC-MAIN-2019-04",
)


def deterministic_collections(year: int):
    if int(year) == 2019:
        return [(ident, f"https://index.commoncrawl.org/{ident}-index") for ident in CC_2019]
    # For a future year, retain the original dynamic discovery rather than
    # pretending a catalogue we have not verified exists.
    return legacy._commoncrawl_collections(year)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2019)
    ap.add_argument("--max-live-checks", type=int, default=180)
    args = ap.parse_args()
    if args.year == 2019:
        legacy._commoncrawl_collections = deterministic_collections
    return int(legacy.run(year=args.year, max_live_checks=args.max_live_checks) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
