# UK auction coverage checkpoint — 7 November 2026

## Scope and current verdict

All UK auction houses, their branches and trading names; every property sector;
current individual lots plus the preceding twenty years of available historical
appearances, retaining older evidence too. National coverage is NOT yet verified.
A commercial website filter is not permission to discard residential or land records.


## Persisted historical gain — 12:17 UTC

The reusable retained-grid runner reconciled eight Auction House Online events and
all 44 visible cards/details from 26 April through 14 June 2022. Bank commit
[fb9837e](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/fb9837e80b8e709b8c0f07e6d7e9b0c8e60eeb87)
added 18 net appearances and 18 exact-dated address records inside the twenty-year
window. One was commercial/mixed-use. It added 18 guides, three achieved prices
and two rents. Twenty-six exact date/address overlaps were excluded; partial,
undated, future-dated and duplicate-identity gains were zero.

Eight previously unbanked source-event/year inventories (all 2022) and ten complete
catalogue/date states were added. No new operator-year was claimed because Auction
House Online 2022 was already represented. The two-card 31 May event was wholly
duplicate and therefore added no appearances.

Initial run [42371001260](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42371001260)
failed closed with zero growth because the manifest reached `main` before its
source definitions. Commit
[26aaa5e](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/26aaa5ec80c52e07e228498face3e201ba29047b)
merged definitions and assertions atomically; successful run
[42371351914](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42371351914)
then banked the evidence. This is recorded as a corrected integration route, not
growth attributed to the failed run.

Exact-revision publication
[42371824997](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42371824997)
passed GitHub Pages and `auctiongeek.co.uk` verification. Totals are now 311,440
appearances, 300,487 address records, 303,175 in-window appearances, 105,509 guides,
112,183 achieved prices and 4,709 complete catalogue/date states.

Next target: the persisted, untriggered 41-card batch across six first-party
catalogues dated 15 March-19 April 2022. National completeness remains false.

Writer-protection check: restarted current scan
[42344862311](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42344862311)
completed successfully and revalidated 913 published rows with zero fresh
reclassifications; the retained snapshot reports 913 published and 1,787 historical
properties. History-bank run
[42371537066](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42371537066)
also completed successfully. No duplicate scan or bank job was launched. The separate
commercial-filter freshness failure remains a source-warning checkpoint, not evidence
that all-sector banked appearances were lost; intentional residential/land exclusions
and stale-date rows remain distinct from missing source URLs.

## Persisted historical gain — 11:25 UTC

The reusable retained-grid runner reconciled eight Auction House Online events and
all 67 visible cards/details from 21 June through 9 August 2022. Bank commit
[502a671](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/502a67172395483fba29b9465f20f7ee614cda1d)
added 34 net appearances and 34 exact-dated address records inside the twenty-year
window: two commercial, zero mixed-use, five land, ten residential and seventeen
unknown. It added 34 guides, two achieved prices and three rents. Thirty-three exact
overlaps were excluded; partial, undated, future-dated and duplicate-identity gains
were zero. Eight source-events and 18 complete catalogue/date states were added;
the Auction House Online 2022 operator-year was already represented.

Publication run
[42367413004](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42367413004)
passed GitHub Pages and `auctiongeek.co.uk` verification for the exact bank
revision. Totals are now 311,422 appearances, 300,469 address records, 303,157
in-window appearances, 105,491 guides, 112,180 achieved prices and 4,699 complete
catalogue/date states.

The preceding preparation-branch continuation banked source snapshots but added
zero appearances. It is recorded as a non-growth route, and historical push
collection is now restricted to `main` so preparation branches cannot launch
collectors.

Next target: the persisted, untriggered 44-card batch across eight first-party
catalogues dated 26 April-14 June 2022. National completeness remains false.

Current commercial-filter freshness run
[42364875201](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42364875201)
failed independently: Allsop, Clive Emson, Barnard Marcus, Knight Frank, Under The
Hammer, Maggs & Allen, Prime Property Auctions, Shonki Bros, Agents Property
Auction and Greenslade Taylor Hunt lacked a successful current collection or showed
a candidate/publication drop. This is a current-filter warning, not a loss of the
all-sector permanent history bank, and it is not treated as historical growth.

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

## 02:07 UTC follow-through checkpoint

- Fresh all-sector scan [42279226136](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42279226136) completed successfully, validated a source-fresh 917-row published snapshot and retained 1,782 historical rows. Permanent bank run [42325686136](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42325686136) then added **140 address-bearing property identities and 432 individual source-backed auction events**, while enriching 2,319 existing events; bank commit: `9a0cec6f78032cb6e918d8219829a943c7308a0b`.
- The bank now contains 23,643 properties and 28,387 events, all with source URLs. Its emitted validation did not break the 432 new events down by twenty-year date, sector, guide, achieved price or rent, so no such subsets are inferred. This current all-sector banking remains distinct from the commercial website filter and from historical-corpus totals.
- Publication run [42325939267](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42325939267) completed successfully on both GitHub Pages and `auctiongeek.co.uk`. Serial follow-up current scan [42321141418](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42321141418) remains inside production collectors. No duplicate scan, bank, publisher or historical writer was launched.
- While those protected jobs run, commits `6386c6f9d1688909660ef543c55c5d7fc390aa4f` and `17655d4664a4c20ab5645737b5386f1fac89f940` added contracts and regression expectations for the next four first-party Auction House Online catalogues: 6 June (24 cards), 30 May (20), 23 May (16) and 16 May 2023 (25). Unwatched manifest `config/retained_grid_batch_next.json` in commit `444d719c68ff00073dd0d9120997e266c6240891` preserves the **85-card** follow-on batch without triggering it.
- Next concrete historical action is unchanged: after the active current scan and publisher clear, run the already prepared **111-card** 4 July to 13 June manifest once, reconcile all card/detail denominators, merge/rebuild once and publish once. Promote the unwatched 85-card batch only after that first batch banks or records a bounded source-specific blocker.
- National completeness remains **false**.

## 03:18 UTC follow-through checkpoint

- Serial follow-up current scan [42321141418](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42321141418) completed successfully with a source-fresh 919-row snapshot. Permanent current-history bank run [42329676626](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42329676626) added **3 address-bearing property identities and 3 individual auction events**, added 3 guide-bearing events, added 0 achieved-price events, and enriched 2,752 existing events. It did not emit reliable date-window or sector deltas, so none are inferred.
- The scheduled historical continuation [42328689221](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42328689221) added 0 appearances and is not claimed as growth.
- Protected manifest run [42332005368](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42332005368) then reconciled all **111 cards and 111 detail pages** across four June/July 2023 catalogues. After excluding 71 exact date/address overlaps it banked **40 appearances**, **40 addresses**, **40 exact-dated in-window addresses**, 2 commercial, 1 mixed-use, 40 guides, 4 achieved prices and 0 rents. Partial, undated, future-dated and duplicate-identity additions were all 0. Bank commit: `9b3ac73fbe418db392c7157f6d174c5e3bcb7068`.
- Publication run [42332577003](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42332577003) passed both GitHub Pages and `auctiongeek.co.uk` live-data/indexing verification.
- The manifest-trigger commit also caused a current-scan workflow [42332005410](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42332005410) to enter production collectors through the repository's broad push trigger. No duplicate historical batch was started. The separate **85-card** May/June manifest is marked ready but held until that scan, its permanent-history bank and publication chain resolve.
- National completeness remains **false**.


## 04:50 UTC historical batch checkpoint

- Protected manifest run [42338076003](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42338076003) reconciled all **85/85 cards and 85/85 detail pages** across four first-party Auction House Online catalogues: 6 June, 30 May, 23 May and 16 May 2023.
- After excluding 53 exact date/address overlaps, it banked **32 appearances**, **32 address records** and **32 exact-dated address records inside the twenty-year window**. Sector gains were 1 commercial, 0 mixed-use, 2 land, 13 residential and 16 unknown. Evidence gains were **32 guides, 2 achieved prices and 1 rent**. Partial, undated, future-dated and duplicate source-identity additions were all 0.
- Per-event net gains were: 6 June +15 appearances/+15 guides/+1 achieved price/+1 rent; 30 May +5/+5/+0/+0; 23 May +8/+8/+1/+0; 16 May +4/+4/+0/+0. The batch reconciled four source-events and eleven complete catalogue/date states, but added 0 genuine operator source-years. Bank commit: `48c1080b8de55eb4d220e3cef354bdd1f1f9e00d`.
- Corpus totals are now **311,150 appearances**, **300,197 addresses**, **302,885 in-window appearances**, **105,219 in-window guides** and **112,150 in-window achieved prices**. Retained exceptions remain 10,953 partial, 5,018 undated and 152 future-dated. Complete catalogue states are 4,601; 556 remain incomplete/unreconciled and 31 remain fetch/parse failures.
- Exact bank publication [42338549825](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42338549825) passed tests, artifact/source-revision checks, GitHub Pages deployment, `auctiongeek.co.uk` deployment, live property-data checks and indexing checks. The preceding manifest-triggered current-history bank added 0 properties and 0 events and is not counted as collection growth.
- Manifest-only path isolation is now enforced at the current workflow trigger as well as inside its jobs (commits `b990344b7c2fa82b718939f82a1e3d317f8dd037` and `b987dda0881be68efca2bd26ca2f04932418089d`). Future retained-grid manifest promotions do not start the current scanner or snapshot revalidation writer.
- A **79-card** April-May batch (9 May, 2 May, 25 April and 18 April 2023) is serialised behind bounded continuation run [42339526658](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42339526658); intended manifest run [42339578763](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42339578763) remains queued and must not be duplicated. All four event IDs were absent from the appearance bank before promotion.
- The next unwatched target is a **67-card** batch covering 11 April, 4 April, 28 March and 21 March 2023 (events 47008, 46885, 46723 and 46417). Collector contracts and regression expectations are persisted in commits `0739303e581ef78d71b8fbe6ae241f5ccb50adbf` and `2055754ab3aeb42b5a87eb905038e6166cb66be0`; `config/retained_grid_batch_next.json` remains deliberately unwatched.
- National completeness remains **false**.


## 05:47 UTC protected batch follow-through

- Bounded continuation [42339526658](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42339526658) added 0 appearances and is not counted as collection growth; it enriched 6 existing appearances with achieved-price evidence. Its publication [42341325574](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42341325574) passed.
- Protected manifest run [42339578763](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42339578763) reconciled 79/79 cards and details across 9 May, 2 May, 25 April and 18 April 2023. It banked **29 appearances, 29 addresses and 29 exact-dated in-window addresses**, including 2 commercial, 0 mixed-use, 4 land, 5 residential and 18 unknown; evidence gains were 29 guides, 2 achieved prices and 1 rent. Fifty exact date/address overlaps were excluded. Bank commit `e728bf938a701230b8351c51d75a86878d4aaef0`; exact publication [42341809259](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42341809259) passed both public lanes.
- Protected manifest run [42342889781](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42342889781) reconciled 67/67 cards and details across 11 April, 4 April, 28 March and 21 March 2023. It banked **21 appearances, 21 addresses and 21 exact-dated in-window addresses**, including 0 commercial, 0 mixed-use, 3 land, 3 residential and 15 unknown; evidence gains were 21 guides and 3 achieved prices. Forty-six exact date/address overlaps were excluded. Bank commit `2b6e5b2e19cf75c2c910bb4a7d5cc76fd718503d`; exact publication [42343377705](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42343377705) passed Pages, `auctiongeek.co.uk`, live property-data and code/indexing checks.
- Combined batch growth is **+50 net appearances, +50 addresses and +50 exact-dated in-window addresses**. Commercial/mixed-use additions are **2/0**. Actual evidence gains are **+50 guides, +11 achieved prices** (5 on new appearances plus 6 enrichments) and **+1 rent**. New partial, undated, future-dated and duplicate source-identity records are 0; 96 exact overlaps were retained as evidence but excluded from growth.
- Eight source-events and 20 complete surviving catalogue/date states were newly reconciled. Genuine new legal-operator source-years are **0**, because the Auction House regional labels are branches/trading names under AUCTION HOUSE UK LIMITED and operator-year 2023 was already represented.
- Corpus totals are now 311,200 appearances, 300,247 addresses, 302,935 in-window appearances, 105,269 in-window guides and 112,161 in-window achieved prices. National completeness remains **false**.
- The next untriggered target is a **112-card six-catalogue batch**, 14 March to 7 February 2023, persisted in `config/retained_grid_batch_next.json`. Collector and regression contracts are committed as `d64e334b4fb5ac8b2e1042a708b2b1dbb37660b5`, `d13c59c3f984d41cf509379c29e714d41902e111` and `bc06bbf9d4e47c0a01cc9f25f0db1145ad664321`. It has not been launched. All-sector permanent banking remains distinct from the commercial website filter.


## 06:17 UTC active-writer protection and prepared follow-on

- Current all-sector scan [42344862311](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42344862311) remained in production collectors after passing regression tests. It had not yet produced a validated snapshot, permanent-history bank or publication result, so no historical writer was launched beside it.
- Savills bulk run [42344581580](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42344581580) reported 30 retained corpus records, 0 newly discovered rows, one attempted page and one blocker; it committed no corpus change. No growth is claimed and the same blocked route was not retried.
- This checkpoint therefore adds 0 appearances, 0 addresses, 0 exact-dated in-window addresses, 0 commercial/mixed-use records, 0 guide/sale-price/rent evidence, 0 partial/undated/future/duplicate identities and 0 operator source-years. Historical totals remain 311,200 appearances, 300,247 addresses and 302,935 in-window appearances.
- A different, substantial follow-on is now prepared: eight first-party Auction House Online catalogues from 31 January 2023 to 29 November 2022, **120 advertised cards** total. Source contracts and denominator assertions are in commits `cd683ca567e6035f1710288392ccb103a1845e2d` and `61fc5af77f2a20da9d3084b831585a21b0d75d6a`; untriggered manifest commit `778cb08e88522342c6207b154da5c658e2fbb039` keeps it behind the existing 112-card February-March target.
- Next action remains the 112-card batch after the current scan, permanent bank and publication chain clear. National completeness remains **false**.


## 07:12 UTC — six-catalogue retained-grid gain banked and published

- Historical run [42349187635](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42349187635) reconciled all 112 advertised cards across six Auction House Online catalogues dated 7 February–14 March 2023. Permanent bank commit `1231e7a49a058ade571807aefedd4c5b6b3f27ce` was then published by exact-revision run [42349583662](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42349583662); both public and production jobs succeeded.
- Net banked gain: **48 appearances**, **48 dated addresses inside the rolling 20-year window**, **4 commercial/mixed-use** (4 commercial, 0 mixed-use), **48 guide prices**, **5 achieved prices** and **3 rents**. The remaining 64 cards were exact overlaps and were excluded from growth.
- The gain has 0 partial, undated, future-dated or duplicate source identities. It reconciles six source-event inventories but adds 0 operator source-years because Auction House Online / AUCTION HOUSE UK LIMITED 2023 was already represented.
- Totals are now 311,248 appearances, 300,295 addresses and 302,983 in-window appearances; 4,637 source entries are complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Next target:** the tested eight-catalogue, 120-card manifest covering 29 November 2022–31 January 2023 is ready in `config/retained_grid_batch_followon.json` for the next serial run after an active-writer recheck. It has not been launched in parallel.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.


## 08:22 UTC — 120-card November 2022–January 2023 batch banked and published

- Historical run [42353744821](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42353744821) reconciled all 120 advertised cards and detail pages across eight Auction House Online catalogues. Bank commit `7063e9d9b1e9a0508a55d18429e41b991eb606a1` passed exact public and production publication in run [42354279444](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42354279444).
- Net growth: **60 appearances**, **60 dated addresses inside the rolling 20-year window**, **1 commercial and 1 mixed-use**, **60 guides**, **3 achieved prices** and **13 rents**. Sixty exact overlaps were excluded.
- The gain contains 0 partial, undated, future-dated or duplicate source identities. It adds eight reconciled source-events but 0 genuine operator source-years because AUCTION HOUSE UK LIMITED was already represented in 2022 and 2023.
- Corpus totals are now 311,308 appearances, 300,355 addresses and 303,043 in-window appearances; source states are 4,653 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Next target:** eight official catalogues from 4 October–22 November 2022 expose **127 cards**. Contracts, assertions and the untriggered manifest are persisted in commits `ec066d41ac1785e606929dcc9ae8ded847c43d49`, `ccdab7efc2db79a2262000ec760082b089c62ed9` and `0fba710a7879e8a0e84359b9a4214cdbb4d15f48`. It remains serial and untriggered pending the next active-writer check.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.


## 09:28 UTC — 127-card October–November 2022 batch banked and published

- Historical run [42357831601](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42357831601) reconciled all 127 advertised cards and detail pages across eight Auction House Online catalogues. Bank commit `e876b509a1dd7c9d767ad8bccc6e054d9907e1ee` passed exact public and production publication in run [42358407773](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42358407773).
- Net growth: **57 appearances**, **57 dated addresses inside the rolling 20-year window**, **0 commercial and 0 mixed-use**, **57 guides**, **6 achieved prices** and **1 rent**. Seventy exact overlaps were excluded.
- The gain contains 0 partial, undated, future-dated or duplicate source identities. It adds eight reconciled source-events but 0 genuine operator source-years because AUCTION HOUSE UK LIMITED was already represented in 2022.
- Corpus totals are now 311,365 appearances, 300,412 addresses and 303,100 in-window appearances; source states are 4,672 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Next target:** seven official catalogues from 16 August–27 September 2022 expose **62 cards**. Contracts, assertions and an untriggered manifest are persisted on main. Scheduled continuation [42358682725](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42358682725) produced zero new appearances; exact-revision publication [42360482546](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42360482546) completed both public and production jobs. The batch remains untriggered pending one fresh active-writer check.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.


## 10:04 UTC — 62-card August–September 2022 batch banked

- Historical run [42361312678](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42361312678) reconciled all 62 advertised cards and detail pages across seven Auction House Online catalogues. Permanent bank commit `8493c56059ab4068b795b9c7b8b90fa028ccd48e` is preserved. Exact-revision publication [42361647719](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42361647719) passed tests, export and artifact checks but timed out in provider-side Pages deployment. The failed checkpoint remains preserved. Recovery commit `1df885c4bd997195d424f0968b879172c5ccc0f0` extended the documented deployment allowance and recovery run [42363056519](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42363056519) passed both Pages and production verification for the exact bank revision.
- Net growth: **23 appearances**, **23 dated addresses inside the rolling 20-year window**, **1 commercial and 0 mixed-use**, **23 guides**, **3 achieved prices** and **1 rent**. Thirty-nine exact overlaps were excluded.
- The gain contains 0 partial, undated, future-dated or duplicate source identities. It adds seven reconciled source-events and nine catalogue/date states but 0 genuine operator source-years because AUCTION HOUSE UK LIMITED was already represented in 2022.
- Corpus totals are now 311,388 appearances, 300,435 addresses and 303,123 in-window appearances; source states are 4,681 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Next target:** eight official catalogues from 21 June–9 August 2022 expose **67 cards**. Contracts, assertions and an untriggered manifest are ready for one serial run after a fresh active-writer check; no duplicate collector was launched.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.


## 12:53 UTC — 41-card March–April 2022 batch banked and published

- Historical run [42373375014](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42373375014) reconciled all **41 advertised cards and detail pages** across six Auction House Online catalogues dated 15 March–19 April 2022. Archive pagination and detail recovery completed without a source failure.
- Permanent bank commit `ca64e31e9a783a248024ca292c43e144f3eb6a05` passed exact-revision publication [42373710828](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42373710828): both Pages/source-to-live and `auctiongeek.co.uk` live property-data/code/indexing jobs succeeded.
- Net growth is **20 appearances**, **20 addresses** and **20 exact-dated in-window addresses**; commercial/mixed-use is **0/0**. Actual evidence growth is **19 guides**, **0 achieved sale prices** and **1 rent**.
- Twenty-one exact date/address overlaps were retained as evidence but excluded from growth. The gain contains 0 partial, undated, future-dated or duplicate source identities. Six event inventories and ten complete catalogue/date states were added, but genuine operator source-years added are **0** because Auction House Online / AUCTION HOUSE UK LIMITED 2022 was already represented.
- Corpus totals are now 311,460 appearances, 300,507 addresses and 303,195 in-window appearances; 105,528 in-window records have guide evidence and 112,183 have achieved-price evidence. Source states are 4,719 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Next target:** nine official catalogues from 18 January–8 March 2022 expose **43 cards**, including two distinct 1 February event IDs. Collector contracts, strict denominators and an untriggered serial manifest are persisted in `config/retained_grid_batch_next.json`; no next collector was launched beside publication.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.


## 14:08 UTC — 43-card January–March 2022 batch banked

- Historical run [42379602051](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42379602051) reconciled all **43 advertised cards and 43 detail pages** across nine Auction House Online catalogues. Permanent bank commit `c2da6199470905b48e7ba26066bbfc722b6cef3a` preserves the individual dates, prices, outcomes, original URLs and immutable snapshots; exact-revision run [42380214634](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42380214634) passed both Pages and `auctiongeek.co.uk` verification.
- Net growth is **22 appearances**, **22 addresses** and **22 exact-dated in-window addresses**. Commercial/mixed-use growth is **0/0**. Actual evidence growth is **22 guides**, **5 achieved prices** and **0 rents**.
- Twenty-one exact date/address overlaps were retained as evidence and excluded from growth. Partial, undated, future-dated and duplicate source-identity additions are all 0. Nine source-event inventories and 13 catalogue/date states were reconciled, but genuine new legal-operator source-years are 0 because AUCTION HOUSE UK LIMITED 2022 was already represented.
- Corpus totals are 311,482 appearances, 300,529 addresses and 303,217 in-window appearances; 105,550 in-window records have guide evidence and 112,188 have achieved-price evidence. Retained exceptions remain 10,953 partial, 5,018 undated and 152 future-dated.
- **Next target:** nine official catalogues from 2 November 2021–11 January 2022 expose **44 cards**. The collector contracts and untriggered serial manifest are prepared in `config/retained_grid_batch_next.json`; no follow-on collector is launched beside publication. The archive's empty 21 December shell is excluded from the denominator while the separate four-card event remains admitted.
- All-sector permanent banking remains distinct from the commercial website filter. National completeness remains **false**.
