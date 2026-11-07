# UK auction coverage checkpoint — 7 November 2026

## Scope and current verdict

All UK auction houses, their branches and trading names; every property sector;
current individual lots plus the preceding twenty years of available historical
appearances, retaining older evidence too. National coverage is NOT yet verified.
A commercial website filter is not permission to discard residential or land records.

## Verified holdings before this repair

- Historical corpus generated 2026-11-07 00:09 UTC: 311,078 appearances,
  300,125 address records, 167,055 exact address groups and 42,666 repeat groups.
- 4,577 retained catalogues reconciled; 556 incomplete or unreconciled; 31 fetch/parse failures.
- The directory has 567 candidate entries, not 567 proven distinct UK operators.
- The current coverage report tracks 78 source/brand entries. Only four expose
  comparable current commercial-lot denominators; the remaining 74 are unverified.
- Published current snapshot was still dated 2026-11-02 06:34 UTC.
- Reconciled expected/captured commercial URLs in that old snapshot: BidX1 21/15,
  Clive Emson 32/32, Savills 90/86, Strettons 17/16. The 11 unmatched rows include
  intentional residential exclusions and stale-date records, not 11 proven lost lots.

## Repairs implemented

1. Added the same pinned Stripe SDK used by the private application to the shared
   regression dependencies. A real-SDK offline test had prevented current collection
   from reaching the collectors (run 42279226136).
2. Fixed asset classification: agency credits, bidding widgets, neighbouring shops
   and town amenities cannot turn a house into a commercial property. The failed
   6 November candidate contains seven such false positives. Correcting them retains
   their descriptions and records; the remaining Cumbria and National Online rows
   reach 100% image and rich-detail coverage without changing the existing thresholds.
3. Permanent banking now also includes genuine retained residential/land exclusions.
   Interface and search-page exclusions remain ineligible. Repeated banking is
   idempotent; newer collected facts win over stale duplicate rows.
4. Excluded-record identities now include auction date and lot number. Reusing an
   auctioneer URL must not erase an earlier auction appearance or guide price.
5. The owner coverage audit now reports denominator gaps, unmatched lots, stale
   sources and retained non-commercial rows explicitly. It never infers national
   or all-sector completeness from green collector statuses.
6. Full-ancestry checkout now uses Git's blob filter in current scan, revalidation
   and permanent-banking workflows. This retains ancestry for safe rebases and
   candidate checks without eagerly downloading every obsolete evidence-file version.

## Validation and live follow-through

Targeted collection/publication/storage checks passed. The 91-check matching and
storage run includes source-backed Newbury changed-interest and Broadway cross-house
fixtures, neighbouring units, reused URLs and source evidence. The additional owner
coverage and exclusion-retention checks passed. Full-suite verification and production
publication must be recorded separately; a queued/running job is not success.

First repair commits: 3ff49151fbfb36ec5180cc62b8fb36f62e7b93b0 and
eb0750886b2b07f4fd4f70a1c293683ae30a2cbf. Fresh scan 42279226136 was restarted.
Do not republish the stale 6 November artifact as fresh data. Preserve any subsequent
failed candidate artifact and resolve its actual gate failure.

## Remaining programme and acceptance

- Establish the national operator/branch/shared-platform register with first-party
  evidence. Exact directory-name misses are not proof of an absent integration.
- Reconcile each live auctioneer's dated individual lot URLs against captured rows;
  distinguish sector exclusions, expired results, parse failures and missing lots.
- Extend commercial-only discovery to all-sector capture source by source. Banking
  retained exclusions fixes storage but does not capture lots never discovered.
- Resolve the 556 historical catalogue states, missing source-years and uncovered
  auctioneers; batch substantial accessible catalogues rather than repeatedly adding
  one dated workflow step for a tiny shared-platform event. Honour source access limits.
- Bank immutable source evidence with guides and achieved prices kept separate,
  all outcomes retained, missing values null, and exact overlaps deduplicated.
- Validate repeat appearances and related interests on the live site as well as in
  tests. Keep whole buildings, units, freeholds and new leases distinct; prohibit
  price-reduction calculations between materially different interests.
- Preserve owner removal/correction controls and premium entitlements.

The existing hourly historical task remains enabled with this follow-through. Report
net persisted lots and price evidence, not catalogue pages or successful job counts.

## 01:00 UTC follow-through checkpoint

- Permanent current-history bank run [42320434706](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42320434706) safely added **45 property identities and 51 auction events**, with 2,593 existing events updated from retained source facts. Bank commit: `17e515d6e725f11631f9f98321a0cceaf1e2c3f1`.
- The serial follow-up bank [42321141420](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42321141420) added **0** properties and **0** events and re-applied 2,644 updated facts in commit `9fee23196e574aba116b65adcbff9908c47650e2`. It is an idempotency check, not a second collection gain. The bank job did not emit sector, date-window or price-field deltas, so none are inferred.
- Snapshot-repair run [42320435220](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42320435220) passed checkout, regression tests and candidate recovery, found no newer production candidate, revalidated the 906-row snapshot, and then stopped on the explicit freshness gate because its source timestamp remained 2 November 2026. It published nothing and is not retried.
- Fresh all-sector scan [42279226136](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42279226136) remains inside production collectors. Follow-up scan [42321141418](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42321141418) remains pending behind the production concurrency lock. Their results must be verified before another current-data writer starts.
- Historical collector improvement commit `9e106594863a28e88054b6f4062678ca7c980133` adds a reusable manifest-driven multi-source runner and aggregate per-field gain reporting. Regression commit `2036afb95e1f0f534d3b7687c240a9c423987c6b` covers source contracts and ordered manifest deduplication; workflow commit `955799f0d18530adaa83c43bae8d3127cdfa5b93` adds one generic batch step rather than one step per auction date.
- Prepared manifest commit `a4c14f29eeea621e977a0360b25fd2f1e6040265` targets four accessible Auction House Online catalogues: 4 July, 27 June, 20 June and 13 June 2023, with **111 published visible cards** in total. It remains deliberately dormant while current collection is active; no historical appearance growth is claimed from the manifest yet.
- Next concrete historical action after current lanes clear: trigger this one protected manifest batch, verify each catalogue/card/detail denominator, merge and rebuild once, publish once, and report exact appearances, in-window dated addresses, commercial/mixed-use, guides, achieved prices, rents, partial/undated/future rows and excluded overlaps.
- National completeness remains **false**.

