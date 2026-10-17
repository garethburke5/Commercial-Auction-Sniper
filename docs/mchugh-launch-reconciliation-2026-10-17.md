# McHugh current catalogue repair — 17 October 2026

The 20:44 UTC production snapshot discovered 208 McHugh lot pages but recorded 198 missing-particulars failures and ten past-sale exclusions. It retained six last-known-good rows and published no current qualifying rows from that source.

The current first-party template uses `h3.lot-details-heading` and sibling sections. The old collector expected the different `lot-data-heading` layout. Commit `f73d32ba2e16e0d09c608afe2cc4814b56e224fa` supports both, requires substantive description evidence and reads only property fact sections. Bidding-help modals and neighbouring lots are excluded from classification and income extraction.

An explicit early sold-prior/withdrawn/postponed result can show an earlier result timestamp. Where the current catalogue heading evidences the future sale date, the collector now retains that advertised auction date rather than dropping the lot. It does not invent a date or treat generic bidding-help text as a lot result.

## Fresh first-party check

The repaired collector read the current 21 October catalogue at `https://www.mchughandco.com/current-auction`:

| Measure | Result |
| --- | ---: |
| Discovered and inspected lot pages | 208 |
| Detail failures | 0 |
| Past-sale exclusions | 0 |
| Commercial candidates | 9 |
| Mixed-use candidates | 1 |
| Other classification exclusions | 198 |

All ten candidates passed the existing publication exclusion function. Passing rents extracted included £25,700 at 22 Market Square, Shipley and £28,000 at 7–11 North Street, Exeter. These are source particulars, not independently verified income or investment-report conclusions. The candidate set contained no terminal commercial lot, so real terminal-state evidence is limited to inspection of the source and focused regression fixtures.

Twenty-five focused collector/withdrawal tests passed; the full suite passed 866 tests and 19 subtests. Fresh collection used the existing fetch route, retries and four-worker limit.

## Publication status

GitHub publication run `39069165519` was queued behind an existing production scan at this checkpoint. The new code was live on Render at 21:04:23 UTC, but that alone does not refresh catalogue data. Do not mark these ten refreshed candidates as published until the collection, validation and public deployment finish.

The wider source register remains open. Barnard Marcus's latest available-lot check now matches 135 advertised and 135 observed cards, although two detail failures remain. Under The Hammer still returns HTTP 403 from its existing feed and retains eligible last-known-good rows; its access restriction was not bypassed.
