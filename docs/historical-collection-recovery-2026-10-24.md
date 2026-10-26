# Historical collection recovery — 24 October 2026

## Scope and acceptance

The programme covers individual auction appearances across UK auction houses, branches and trading names, for every property sector and the preceding twenty years. Retain older evidence too. Catalogue discovery, successful collection attempts and source-label counts are not proof of national completeness.

Keep guide and achieved prices distinct. Preserve sold prior, sold after, unsold, withdrawn and postponed outcomes; never manufacture missing prices. Preserve original evidence and separate changed legal interests when matching properties.

## Implemented recovery

- The historical workflow runs hourly with a 20-minute rotating collection budget, a per-task timeout, and a single concurrency group. It no longer stops after four fast tasks.
- A rebuild-only workflow mode publishes already banked evidence without waiting for another collection batch.
- The rotation contains 52 collection tasks, including the previously omitted Barnard Marcus continuation. This is a task count, not a count of distinct auction houses.
- Every attempt records its outcome, elapsed time and diagnostic tail. Cursor checkpoints survive failed tasks.
- Symonds & Sampson reads its official XML sitemap and property pages, retains disappeared pages, and checkpoints successful lot records individually.
- Swift retains validated dated lot cards when the catalogue headline count disagrees, while keeping the catalogue incomplete.
- Barnard Marcus discovers dated catalogues from its official sitemap, prioritises missing catalogues, reuses reconciled legacy captures, checkpoints API pages, retains individually identified rows despite inconsistent totals, and recovers omitted identities from official detail pages.
- Incomplete source-corpus catalogues now produce explicit coverage-gap records. A stored lot cannot silently make an incomplete catalogue disappear from monitoring.
- Source-corpus banking preserves sold-prior and sold-after outcomes. Barnard Marcus and Pugh unsold parsing cannot treat the substring “sold” as a sale.
- `data/auction_history/source_register.json` records external directory discovery, conservative links to corpus labels, retained years and price counts, collector failures and incomplete catalogues. Directory entries require UK geography, branch and trading-name reconciliation before they can serve as a national denominator.

## Measured checkpoints

The pre-recovery production checkpoint at 16:14 UTC contained 279,143 individual lot records, 1,868 reconciled retained catalogues and 621 incomplete or unreconciled catalogue states. It included future auctions and must not be described as 279,143 historical properties or unique buildings.

The local database rebuild at 21:24 UTC passed SQLite integrity checking and contained 279,503 appearances: 341 newly captured Barnard Marcus October lots, 12 Symonds & Sampson records and 7 Swift records above that baseline. This is a local recovery checkpoint; production publication must be verified separately. The subsequent 21:28 UTC rebuild contained 279,507 appearances after recovering all four missing sitemap identities. The 364 additional records and their evidence were committed in `4a7dc9227f2f5a9bf749ab68bea1462f9e071fb6`. Production rebuilding was still pending at that point.

The official Barnard Marcus October API returned conflicting totals of 345 and 347 with overlapping page results. The initial 341 captured identities therefore did not establish catalogue completeness. The sitemap supplied four further identities, all recovered from their official detail pages; the final 345 captured rows match that sitemap but the API's conflicting 347 count remains unresolved.

## Remaining programme

1. Reconcile directory identities against the source registry; do not equate 567 directory entries with 567 active UK auction houses.
2. Resolve recorded collection failures, including blocked archive pages and retired or redirected domains, source by source.
3. Reconcile each retained catalogue against its published lot inventory and investigate every shortfall.
4. Extend each auctioneer backwards through all available years, including Savills before the modern catalogue platform. Existing 2013 rows alone do not prove complete 2013 coverage.
5. Quantify missing dates, addresses, guides, achieved prices and rental evidence separately; unavailable evidence remains explicitly unavailable.
6. Verify downstream timelines, exact versus related-interest matching and publication. A rebuilt historical corpus is not itself proof that every record is visible on the public property page.

Do not mark the national programme complete until auctioneer coverage and available source-by-source catalogue inventories reconcile. No completion date has been established for inaccessible or undiscovered historical sources.

## Continuation: Agents current table and First for Auctions archive

- The usable unfiltered Agents Property Auction page banks all 35 visible Newcastle September 2026 sold-result rows. They are 35 address records with 35 achieved prices and no guides. The source publishes only a month, so all 35 retain null auction dates; no record is counted as a newly dated 20-year appearance. One row explicitly names a commercial use and 34 remain sector-unknown rather than being inferred residential from postal-address wording. The historical Newcastle/Cumbria filters remain terminal because submitting `a_sub` returns HTTP 500; they are not retried by default.
- First for Auctions exposes a separate complete EIG past-lots grid. All 28 pages reconcile exactly to the published 1,377-row denominator and 1,377 distinct stable lot IDs. The banked records comprise 1,377 addresses, 1,371 exact-dated appearances through 26 October 2026, six future-dated appearances, 1,078 achieved prices and no published index guide prices. The evidenced commercial/mixed-use subset is 28; residential 1,229, land 24 and unknown 96. Nine operator-years, 2018–2026, are newly represented. Five postponed, ten unsold and four withdrawn results remain distinct from sold outcomes.
- Combined net growth from these sources is 1,412 address appearances. There are no partial or duplicate-derived additions. The next concrete growth target is another uncovered EIG white-label with a reconciled public past-lots denominator, prioritising the largest accessible retained grid rather than refreshing these completed captures.

## Consolidated recovery checkpoint

The 21:49 UTC local rebuild contained 279,698 records, 555 above the 16:14 production checkpoint. Individually checked additions: Barnard Marcus 345, Bond Wolfe 175, Harman Healy 13, Swift 7, Symonds & Sampson 12 and Anderson & Garland 3. These are lot/result records, not unique buildings or a claim that every added record is dated historical evidence. Symonds includes future/undated listings; Anderson selected results can lack dates.

Harman Healy reconciled 1,520 retained cards across 31 pages after invalidating cached pagination when its total changes. This establishes the retained 2020–2026 grid, not twenty-year completeness. Anderson & Garland checked 49 retained listing URLs, retained 29 selected results, and enriched four records with exact auction dates. Successful and failed detail checks now checkpoint so bounded runs can resume.

The first widened production run attempted 45 tasks in 20 minutes: 36 completed, eight failed and one timed out. It found 39 new Cottons appearances, one Pugh appearance, seven Swift records and twelve Symonds records, and downloaded a 175-lot Bond Wolfe source file. Its publication failed on concurrent generated-file conflicts. Its artifact path also exposed a stale single-file database backup after failure; do not use that artifact as evidence of the newly collected count.

Publication now preserves a uniquely named recovery branch before rebasing, stages all historical source-corpus JSON files, banks those files before rebuilding, rebuilds again if main contributes additional source records, and restores the new oversized database before artifact upload even when publication fails. A rebuild-only mode avoids another collection delay when publishing already saved records. Retained failed checkpoint branches require reconciliation, not deletion of their evidence.

The existing hourly Auction History Capture research automation was resumed on 24 October with the all-auctioneer scope and instructions to improve actual collection, recover publication checkpoints, investigate uncovered sources/years and verify persisted output. Other paused automations were left alone. The GitHub collector is separately scheduled hourly; neither schedule establishes national completeness.

## Verified consolidated build

The successful 21:52 UTC production checkpoint published 279,547 records. The later 22:04 UTC rebuild in run `40136239889` combined the saved recoveries with 39 Cottons additions and one Pugh addition, reaching **279,738 records**, 595 above the starting checkpoint. Its downloadable artifact `12578100573` was retrieved and independently checked: the SQLite `appearances` table contains 279,738 rows and `PRAGMA integrity_check` returns `ok`. There are 269,368 addressed records, 10,370 partial records and 624 incomplete or unreconciled catalogue states.

That run's database publication failed with an HTTP 500 while pushing the checkpoint branch. The artifact is valid; it must not be described as a successfully published main-branch database. Subsequent publication retries fetch the current remote before negotiating, use bounded retry handling, and avoid unnecessary OCR installation for rebuild-only jobs. Final main-branch publication remains a separate verification step. The 270 collector tests and 44 continuation/storage tests passed in the consolidated build.

**Publication verified at 22:08 UTC:** run `40137085354` successfully completed its publication step. Main-branch `progress.json` now reports 279,738 records, generated at `2026-10-24T22:07:43.451699+00:00`; the published checkpoint commit is `df4d0e39c92a06ee2532f6c79a882c1a3fe94f3c`. The 595-record gain is therefore published, rather than merely retained in an artifact. This does not establish that all records have appeared on live property timelines, or that national collection is complete.


## Checkpoint: Barnett Ross October 2016 and collector-loop repair

Published corpus checkpoint `0cc1ec049a192248e496f236acd71b7efa28f203`:

- 279,794 individual auction appearances: 269,425 address records and 10,369 partial lots.
- Net change from checkpoint `df4d0e39c92a06ee2532f6c79a882c1a3fe94f3c`: +56 appearances, +57 address records and -1 partial lot after one retained partial was safely upgraded to an address record.
- Source gains were Barnett Ross +54, Barnard Marcus Auctions +1 and Pugh Auctioneers +1.
- Barnett Ross October 2016 is now reconciled at 54/54 visible first-party rows and marked complete. All 54 are address records. The source publishes only the month, so every exact auction date remains null (`month_only_unresolved`) rather than being inferred.
- Total undated appearances are 4,202, up by 55 in this checkpoint. Complete catalogue states are 1,873; 625 remain incomplete or unreconciled and 116 current fetch/parse failures remain.
- The Anderson & Garland collector now continues its finite retained-listing reconciliation when the selected-results marketing page fails. A fallback reference regression exposed by the first live run was corrected.
- Network Auctions' first-party replacement page establishes that the operator joined BTG Eddisons in 2025 and the old legacy archive was removed. The collector now treats that as a terminal migration only when its 1,202 saved appearances and 34 complete legacy catalogue states already exist; it preserves them rather than repeating a zero-result failure.
- The historical workflow now treats its own `Bank historical auction lot records and source evidence` commit as terminal, preventing recursive bounded collectors.
- Both historical validation suites and the rebuilt database/artifact workflow passed in run `40143681854`. The bounded collector was deliberately skipped during this repair validation.
- National completeness is not claimed: 523 of 567 directory entries still require operator/branch/shared-platform reconciliation.


## Checkpoint: blocked-source semantics, Cottons repair and directory aliases

Published repair commits `2bffe96c143e07381d47373ccdcd670016a0738c` and `b2e142fcbe8903bd6e9b3ed14ebcb4f2c2dd987a`, followed by verified generated checkpoint `66c86519c2047c3392c31b56c7afd66590b253be`:

- Corpus totals remain **279,794 individual appearances**, comprising **269,425 address records** and **10,369 partial lots**. There was no net lot-count gain in this repair-only checkpoint. **4,202 appearances remain undated**.
- John Francis now preserves 1,407 retained appearances and already-complete catalogue states when the retired archive responds HTTP 403. That condition is recorded as a refresh blocker rather than a false collection failure.
- Swift now preserves safely banked visible rows when the archive's published denominator differs, records the discrepancy explicitly, and does not repeat unchanged detail requests until the first-party archive snapshot or denominator changes.
- Network Auctions completed cleanly while retaining 1,202 appearances and 34 complete legacy catalogue states under its verified BTG Eddisons migration state.
- The Cottons parser now recognises inline TCPDF `LOT` markers, requires the exact published 1..N sequence, and preserves a genuinely unpublished guide as null. It records catalogue-check evidence separately from price evidence, preventing a null guide from being treated as a parser failure. Admission/storage validation passed; the next normal collection pass must bank the repaired July and April 2026 catalogue checks before any enrichment count is claimed.
- Ten high-confidence trading-name mappings were added with first-party relationship evidence: Allsop Residential, Bagshaws Residential, Barnard Marcus, Brown & Co, Dedman Gray Auctions, Edward Mellor Auctions, Goldings, Pattinson Property Auctions, Sharpes Property Auctions and Sutton Kersh Auctions. The rebuilt source register reduced unlinked directory entries from **523 to 513**, while every mapped entry remains marked partial and twenty-year completeness remains false.
- The failed intermediate Cottons syntax publication was replaced atomically; the admission/storage suite, database rebuild, database packaging, source-register reconciliation, checkpoint publication and artifact retention all passed in workflow run `40147100313`.

Remaining national position: 1,873 complete retained catalogue states, 625 incomplete or unreconciled states and 116 current fetch/parse failures. Directory reconciliation and source-by-source lot inventories remain incomplete.

## Checkpoint: Cottons exact-guide reconciliation and further directory aliases

Published repair commits `c3c565d14af28527032e7f9c38b0d803011afe7d` and `d301bba1a629ecff41f62e3f3b6bafefe303f863`, followed by verified generated checkpoint `ee4138f5a787e99d2a22651f63e9cf1c1b684f04`:

- Corpus totals remain **279,794 individual appearances**, comprising **269,425 address records** and **10,369 partial lots**. This checkpoint added no net appearances; **4,202 appearances remain undated**.
- The Cottons PDF parser now requires uppercase `LOT n` catalogue markers, so lowercase legal-condition prose such as “lot 1” no longer creates a false duplicate-lot failure. The admission/storage regression suite passed.
- Both known 2026 Cottons catalogues now reconcile exactly: 39 lots for 21 October and 44 lots for 9 September. The collector checked **83 appearances**, retained **122 Cottons records with catalogue-guide evidence** across the corpus, and recorded no Cottons failures.
- `Pughs` is now explicitly linked to the retained `Pugh Auctioneers` corpus label and `Symonds & Sampson LLP` to `Symonds & Sampson`. The rebuilt source register reduced unlinked directory entries from **513 to 511**. These remain partial holdings, not twenty-year completeness claims.
- The historical workflow now also triggers when either `config/source_registry.json` or `config/historical_auctioneer_directory.json` changes, ensuring registry-only reconciliation repairs receive the same bank/rebuild verification.
- The normal rotation completed 25 of 27 tasks in the tranche. Pugh remains incomplete because current detail pages do not expose exact lot/date pairs for many retained identifiers; BidX1 reached the per-task timeout. No batch was discarded. Symonds & Sampson completed for its currently exposed sitemap scope only.
- Full workflow run `40154620394` passed banking, database rebuild, packaging, source-register reconciliation, checkpoint publication and artifact retention. Current national state is **1,873 complete retained catalogue states**, **625 incomplete or unreconciled states**, and **110 fetch/parse failures** (down from 116).

National completeness remains unverified; source-by-source lot inventories, 511 directory candidates, Pugh pagination/detail recovery and BidX1 bounded recovery still require work.

## Checkpoint: BidX1 bounded-refresh repair

Published collector repair `488f4f05fe517e37931ff4e8ae870e3ee65d39a8`, regression correction `921282842544ccf8024ef139b56d5cabd683faee`, targeted verification commit `ce83a5210ca89eec418eebfdd10a8821a376cf86`, and generated checkpoint `3a30117b2b4a5a438871e5463c8110d4dda4c225`:

- BidX1 no longer re-downloads every property detail page on an unchanged completed archive. Each of the **43** first-party auction-ID indexes is still fetched and reconciled against its published denominator and exact property-ID set; saved detail evidence is reused only when every one of the corresponding banked appearances is present.
- The targeted live run completed BidX1 in **19.27 seconds**, versus the prior 197-second timeout. It reconciled **43/43 catalogue states**, retained **294 appearances** (**164 residential**, **130 commercial**), reused **294 detail snapshots/appearances** after live index validation, and recorded zero BidX1 failures.
- Corpus totals remain **279,794 individual appearances**, comprising **269,425 address records** and **10,369 partial lots**. There was no net lot-count gain and **4,202 appearances remain undated**.
- The admission/identity suite, continuation/storage suite, bank, database rebuild, packaging, source-register reconciliation, checkpoint publication and database artifact retention passed in workflow run `40158610505`.
- National state remains incomplete: **1,873 complete retained catalogue states**, **625 incomplete or unreconciled states**, **511 unlinked directory candidates**, and **131 current source errors** after the full refresh. The largest current error concentrations are Barnard Marcus (62), Symonds & Sampson (31), Edward Mellor (13) and Cottons (12); these are the next repair targets rather than evidence of completion.

BidX1's timeout is resolved, but no national-completeness claim is made.



## Checkpoint: Barnard Marcus exact sitemap identity reconciliation

Published collector repair `7128123284ee152606b0badc65174ab9bd1b93f7` and generated checkpoint `fb4d7613121fc3b1418eeb0d29f8c4cca3930279`:

- The collector now treats the retained first-party sitemap lot URLs as the stable property-ID inventory when SearchApi totals and page membership drift during traversal. A saved catalogue is promoted only when its unique banked property-ID set exactly equals every sitemap lot identity; missing, extra, or duplicate rows still prevent completion.
- Four previously partial 2026 catalogues were reconciled from already-banked rows without re-downloading their detail pages: 19 May (346), 28 July (358), 10 September (366), and 15 October (345). All four have zero missing or extra identities. Their 62 SearchApi count/duplicate diagnostics remain preserved separately as provenance rather than active completion errors.
- Barnard Marcus now has 20/20 currently retained sitemap catalogues complete, 6,701 appearances, no remaining catalogue failures, and no net appearance gain in this repair.
- Corpus totals remain 279,794 individual appearances: 269,425 address records, 10,369 partial lots, and 4,202 undated appearances. Complete catalogue states increased from 1,873 to 1,877; incomplete/unreconciled states fell from 625 to 621; current source errors fell from 131 to 69.
- Admission/identity tests, continuation/storage tests, bounded collection, source banking, database rebuild, packaging, source-register reconciliation, checkpoint publication and database artifact retention passed in workflow run `40160743199`.

National completeness remains unverified: 621 catalogue states, 69 current source errors, and 511 unlinked directory candidates remain.

## Checkpoint: Phillip Arnold retained-table reconciliation

Published collector repair `daeb7ac76d52e34d765b94ba2bade5f0e3e64ca6` and generated checkpoint `6860d22eb163bb6c64942e05448c38561cddf911`:

- All **120** retained first-party Phillip Arnold result pages were fetched and reconciled. Their unpaginated tables contain **2,416 unique appearances**: **2,389 address records**, **27 partial lots**, and **no undated records**, spanning 24 July 2007 to 17 September 2026.
- The site's separately published `Lots Offered` statistic differs from the visible retained result-table row count on 118 pages and is absent on two. It commonly excludes rows whose later state is withdrawn, reoffered, sold prior or unavailable. The statistic is now preserved verbatim but is not misrepresented as the table-row denominator.
- Completion is established only for the retained first-party publication: all visible table rows have unique source identities, no pagination controls are present, and the captured count exactly equals the visible source-row denominator. An unexpected pagination control now fails collection rather than allowing false completion.
- The repair added no appearances. Corpus totals remain **279,794 appearances**, comprising **269,425 address records**, **10,369 partial lots**, and **4,202 undated records**.
- Complete retained catalogue states increased from **1,877 to 1,997**; incomplete or unreconciled states fell from **621 to 501**. Current fetch/parse failures remain **69**, and **511** directory candidates remain unlinked.
- The collector regression suite, source banking, database rebuild, packaging, source-register reconciliation, checkpoint publication and database artifact retention passed in workflow run `40164140959`.
- The source-specific push route is explicitly excluded from the normal bounded rotation and unrelated Cottons enrichment on future runs; this prevents a named repair from consuming its budget before reaching its target.

Bagshaws was inspected as the next large incomplete-state cluster. Its collector deliberately retains row-level cards/results without an original catalogue denominator, so those 50 states were not promoted merely because they have no fetch errors.

National completeness remains unverified. The 501 remaining catalogue states and 511 unlinked directory candidates still require source-by-source and operator/branch/shared-platform reconciliation.

## Continuation: checkpoint publication, Savills and Swift reconciliation

- A queued historical run based on a stale workflow tree completed collection and database rebuilding but GitHub refused its recovery-branch push because the stale tree appeared to modify the workflow without `workflows` permission. The workflow now moves scheduled jobs to current `main`, rebases the data-only commit before the recovery push, and creates a verified Git bundle artifact before any remote publication attempt. This preserves every collection batch even when branch publication is rejected.
- Savills auction `savills:3` (16 December 2019) exposes 110 unique lots across two fully traversed pages (100 plus terminal 10), while its property-type filter sums to 106 because four visible property-type IDs are absent from that filter. The collector now accepts only this guarded under-reporting shape: every advertised page captured, full preceding pages, non-empty terminal page below the page size, and no duplicate source IDs. Shortfalls and non-terminal full pages remain incomplete.
- Swift auction `swift:85367` (14 October 2026) publishes “Lots sold 4 of 6” but retains seven result cards: four sold/sold-prior, two unsold and one withdrawn. The collector now reconciles the six offered rows separately while retaining the withdrawn appearance. Two older first-party cards with stable IDs—lot 3, 5 Roman Way, Liverpool, and lot 4, 35 Tavistock Crescent, London—are present in a retained earlier snapshot but absent from the latest page; the collector now recovers such snapshot-only rows with original provenance instead of silently losing them.
- The source-specific tests passed. The two Swift snapshot-only records were subsequently banked and verified in the published checkpoint documented below.

National completeness remains unverified; these repairs reconcile two source semantics and strengthen checkpoint recovery, not the remaining auctioneer/year inventory.


## Checkpoint: Swift retained-snapshot recovery and reproducible storage validation

Published Swift data checkpoint `d2ce21036bc998ee173458f6a63154f67a328b8f`, deterministic storage-test repair `cd6c6eab3b8773531d1ca8f87784c0a2955bd625`, and generated checkpoint `8b9fedad7d6cb0c235142e8dd4b4f2e4355a4b97`:

- The retained earlier first-party Swift snapshot contributed two dated address appearances that had disappeared from the current result page: source ID `365218`, lot 3, 5 Roman Way, Liverpool, L33 9TA; and source ID `368877`, lot 4, 35 Tavistock Crescent, Westbourne Park, London, W11 1AZ. Both preserve 14 October 2026, their original lot URLs, guides, postponed outcomes and exact snapshot provenance.
- Swift auction `swift:85367` now contains **9** appearances: 2 sold, 2 sold prior, 2 unsold, 2 postponed and 1 withdrawn. Its separate published statistic of four sold from six offered lots is reconciled without discarding the withdrawn or snapshot-only rows.
- Corpus totals are now **279,796 individual appearances**: **269,427 address records**, **10,369 partial lots**, and **4,202 undated appearances**. This checkpoint is a net gain of **2 address appearances**; partial and undated counts are unchanged.
- Complete retained catalogue states increased from **1,997 to 1,998**; incomplete or unreconciled states fell from **501 to 500**; current source errors fell from **69 to 68**. Savills `savills:3` remains pending a normal source refresh before its guarded pagination reconciliation can change generated state.
- Workflow run `40169972885`, attempt 2, passed both regression suites, source banking, database rebuilding, packaging, source-register reconciliation, checkpoint publication and artifact retention. The broad collector was skipped.
- Artifact `12589994615` has SHA-256 `ab4db484f1cad597b80a51dbeed023c6b0040232c7b88aa436def0f6dfc1ebcd`. The extracted SQLite database passed `PRAGMA integrity_check`; each recovered source ID occurs exactly once. Its Git bundle also verified successfully and records the complete pre-publication data commit.
- The earlier attempt rebuilt the correct 279,796-row database but publication was blocked by a nondeterministic storage regression fixture: default gzip output embeds the current timestamp. The test fixture now fixes `mtime=0`, matching the production database writer and making repeated archive hashes reproducible.

National completeness remains unverified: 500 catalogue states, 68 current source errors and 511 unlinked directory candidates remain, in addition to uncovered auctioneer/year inventories.


## Continuation: Agents Property Auction archive blocker and Savills refresh

- A new source-specific collector and regression coverage were added for Agents Property Auction's first-party Newcastle/Cumbria result archive. The public filter advertises 2010–2026 and publishes address-level sold results with achieved prices; it does not publish exact auction days or original catalogue denominators. The collector therefore keeps dates null (`month_only_unresolved`) and never marks these result tables as complete catalogues.
- The February 2012 Newcastle result page was independently verified in a public browser with 65 address rows, including achieved prices and one undisclosed result. The archive is not empty.
- Free GitHub collection is materially blocked. Ninety-six venue/month combinations across 2010–2013 were attempted: direct requests returned HTTP 500 even through a persistent serialized browser-like session, while the free reader fallback returned no requested auction heading or result rows. Zero records were admitted. Every attempted URL and error remains checkpointed.
- The collector now treats that unchanged combination as terminal until a materially different free retrieval route exists. This prevents repeated zero-result probes while usable sources elsewhere remain. The directory entry stays unlinked and no national-coverage claim is made.
- The same verified workflow refreshed Savills `savills:3`: complete retained catalogue states increased from 1,998 to 1,999, incomplete states fell from 500 to 499, and current source errors fell from 68 to 67. This is a reconciliation improvement, not a new appearance.
- Published corpus totals remain **279,796 individual appearances**: **269,427 address records**, **10,369 partial lots**, and **4,202 undated appearances**.


## Checkpoint: Cottons split-row recovery and enrichment preservation

Published parser repair `54e3a0777ac05d09a93511e17d0e130c5389a66f`, queued-head/focused-run repairs through `4981edffa31f715cb7cdc74f9e86926092fea806`, and generated checkpoint `bea458cdc75e225b3824fa485eb6da72c8e1d091`:

- Cottons' first-party 21 May 2025 result PDF contains lots 1–53. The previous native-PDF parser stopped at page furniture after lot 36 and did not recognise standalone numeric table cells for lots 37 and 43. The repaired parser now banks all 53 exact lot labels.
- This checkpoint adds **17 dated address appearances**, all for 21 May 2025: no partial or undated rows. The sheet now contains 27 sold, 5 sold after, 4 sold prior, 10 available, 6 not offered and 1 under offer appearances.
- Corpus totals are **279,813 individual appearances**, **269,444 address records**, **10,369 partial lots** and **4,202 undated appearances**. Exact address groups increased to 153,492; they remain grouping keys rather than a count of unique buildings.
- Result-parser states now carry a version. A completed state parsed by an older row-reconstruction algorithm is refreshed instead of being reused solely because its saved 1..N prefix is contiguous. Two focused passes refreshed 31 retained sheets; 101 older states remain queued for bounded version refresh.
- Result refresh now preserves later catalogue evidence (guide ranges, guide provenance, property type and tenure) when it replaces the underlying result row. The recovery checked 776 Cottons appearances against catalogues and retains 800 guide-priced appearances. All 53 May 2025 rows have catalogue-check evidence.
- Three catalogue-specific parse failures remain explicit: 22 May 2024 (46 labels against a headline 47), 13 December 2023 (repeated printed label) and 12 July 2023 (35 extracted labels against headline 34). No speculative lot or guide was created.
- Push-triggered collection now refreshes to current main after concurrency waits, preventing a queued code run from restarting a stale continuation cursor. A focused Cottons path banks successful rows even when other source sheets retain recorded failures, then rebuilds and publishes the database.
- The Cottons regression suite, workflow/storage tests, source banking, database rebuild, source-register reconciliation, checkpoint publication and artifact retention passed in workflow run `40187420567`.

National completeness remains unverified: **499** catalogue states remain incomplete or unreconciled, **67** current fetch/parse failures remain and operator/branch/shared-platform directory reconciliation is unfinished.

## Checkpoint: Cottons publication-defect repair and evidenced operator aliases

Published parser repair `5ffebae40423ce0816017ae98d1541f3b57b4f7d`, focused workflow/alias repair `11dd156dd280edb85d80f67f0a3367bd4cd9b6d3`, and generated checkpoint `1d93a88f6905635e24f6c327f10bfba25b2bbf9f`:

- Three Cottons catalogue discrepancies were resolved from first-party PDFs without inventing rows. The 22 May 2024 catalogue genuinely omits result-sheet lot 12, so 46 catalogue rows are checked and lot 12 remains null/unchecked. The 13 December 2023 repeated parenthesised “(LOT 1)” is promotional footer text, not another lot. The 12 July 2023 catalogue contains late-entry lot 35 despite a stale cover headline of 34 lots.
- The reusable catalogue parser now ignores parenthesised promotional cross-references, accepts an evidence-bounded omitted catalogue row only against an independently parsed complete result sequence, and accepts late entries beyond a stale cover count only when catalogue and result labels exactly reconcile to a contiguous sequence. Regression tests cover all three cases.
- A 16-catalogue focused guide pass increased Cottons records checked against catalogue evidence from 896 to **1,087** and appearances carrying catalogue guides from 917 to **1,100**. Fourteen older catalogues remain explicitly unresolved, primarily because no independent offered-lot total survives; no speculative guide or lot was admitted.
- A 16-sheet result refresh increased complete retained Cottons result states from 46 to **61**. The archive now reports 135 discovered sheets, 71 pending and 2 blocked. One OCR attempt reconstructed 36 already-banked appearances; deduplication correctly produced no net new appearance.
- Six directory trading-name/branch entries now reconcile to evidenced corpus operators: BTG Eddisons Property Auctions, Clive Emson Land and Property Auctioneers, Lambert Smith Hampton (National), and Bagshaws Ashbourne, Bakewell and Uttoxeter. Directory entries not linked to a corpus operator fell from 511 to **505**; this is reconciliation evidence, not six new auctioneers or lots.
- The verified database artifact from workflow run `40193863006` is retained as `historical-auction-lot-database` (341,331,166 bytes; SHA-256 `bf7a209f23bf4160b3f62b8326bd5f2cf7a32c51f016b78ed2a18b0f3a3af186`). Build, source banking, database rebuild, register generation, checkpoint publication and artifact upload all completed successfully.
- Corpus totals remain **279,813 individual appearances**: **269,444 address records**, **10,369 partial lots** and **4,202 undated appearances**. Exact address groups are 153,498 and remain grouping keys, not a verified count of unique physical buildings. Catalogue states remain 1,999 complete, 499 incomplete or unreconciled, with 67 current fetch/parse failures.

National completeness remains unverified. The remaining incomplete catalogue states, current source failures, 505 unlinked directory entries and source-by-source inventory gaps must be reconciled before a national-coverage claim.



## Checkpoint: Cottons validated label-gap and OCR recovery

Published repairs `a1829759633fdfa17160049de39ad26e7ff52ed1`, `e2ddda5c44bda08bddbf2ee05faaa4dcc5ebda16` and `9d82dc84dfd891f7f5e4a756ba920301a81347fc`, followed by generated checkpoint `9dd4ab98b5c3e707600c1b89fb78b362d7da9185`:

- The 10 July 2024 first-party result sheet and catalogue each contain the same 50 lot identities: labels 1–51 with 31 unassigned. The collector now promotes this publication only after exact saved-result/catalogue evidence proves that the same single label is absent from both sources. It records lot 31 as an explicitly unassigned publication label and does not create a synthetic property row.
- Retained native-PDF OCR variants are repaired only at result-row starts: `Al` maps to lot 41, `§2` to lot 52, `§3` to lot 53 and `$2` to lot 52. Existing sequence, duplicate and missing-label guards still apply.
- Five dated address appearances were newly banked; there were no partial or undated additions:
  - 11 July 2013 lot 52, 3 Orchard Road, Erdington, Birmingham, B24 9JL — sold for £166,000.
  - 11 July 2013 lot 53, 5 Dovedale Avenue, Willenhall, West Midlands, WV12 4NA — not offered.
  - 29 October 2013 lot 52, 12 Crusader Close, Oldbury, West Midlands, B69 1EF — sold for £46,000.
  - 3 June 2015 lot 41, Red Lion Cottage, Bell Square, Weobley, Hereford, HR4 8SE — available at £80,000.
  - 15 October 2015 lot 41, 59 Rock Road, Olton, Solihull, West Midlands, B92 7LD — sold for £137,000.
- Published corpus totals are now **279,818 individual appearances**: **269,449 address records**, **10,369 partial lots** and **4,202 undated appearances**. Complete catalogue states increased from 1,999 to **2,003**; incomplete states fell from 499 to **495**; current source failures fell from 67 to **62**.
- Cottons now retains **7,427 appearances** across **94 complete result sheets**; 32 sheets remain pending and 3 blocked. The result-sheet count is not a proxy for properties.
- The focused Cottons suite passes 32 tests. All three workflows passed collection/banking, database rebuild, packaging, checkpoint publication and artifact retention. The final SQLite artifact passed integrity checking and contains the five recovered identities exactly once.
- Final artifact `12600802966` is 301,625,375 bytes with SHA-256 `10fef203aea16bbb913d5d0d7bd203b9ba66dfc85598e943e55a9be4e3ee8a26`.

National completeness remains unverified: 495 incomplete catalogue states, 62 current source failures, 505 unlinked directory entries and uncovered source/year inventories remain.

## Checkpoint: Cottons sequential OCR row recovery

- The Cottons OCR parser now repairs a tightly bounded set of row-start distortions only when the damaged token occupies the exact next numeric sequence slot. This recovered eight dated address appearances without relaxing duplicate or missing-label checks: 17 February 2011 lots 1 and 47; 26 March 2013 lot 11; 25 February 2014 lots 5 and 7; and 4 December 2014 lots 7, 10 and 51.
- The recovered evidence includes achieved prices, available prices and published outcomes. No partial or undated row was added. The 4 December 2014 token `1Q` is now correctly identified as lot 10 rather than retained as a speculative lettered lot.
- Terminal punctuation in published result outcomes is now parsed without contaminating the address. Across refreshed OCR sheets this reclassified 15 previously unknown rows: 14 as sold-prior and one as sold-after. Separating the recovered row starts also corrected five adjacent result/outcome pairings that had absorbed evidence from the following row; price fields remain null unless the source publishes an amount.
- OCR-derived completed states carry an independent OCR parser version and are refreshed when that parser changes. Three bounded passes drained the finite version-refresh queue; the archive now retains **7,435 appearances**, **129 complete result sheets**, no unprocessed pending sheet and three explicit source blockers.
- Three examined first-party result sheets remain unreconciled rather than being treated as missing properties: 6 September 2016 omits labels 24 and 28, 10 September 2015 omits label 54, and 23 October 2012 omits label 51. They require exact matching catalogue-label evidence before their publication gaps can be marked intentional; no synthetic rows were created.
- The hard blockers remain the archive's HTTP 404 for 13 September 2023, the 14 February 2018 image-only sheet with no recoverable table header, and conflicting duplicate OCR evidence in the 28 February 2017 sheet.
- A rebuilt database verifies **279,826 individual appearances**: **269,457 address records**, **10,369 partial lots**, and **4,202 undated appearances**. This is a net gain of eight dated address appearances. Complete catalogue states increased from 2,003 to **2,007**, incomplete states fell from 495 to **491**, and current fetch/parse failures fell from 62 to **58**.
- The focused Cottons suite passes 35 tests. National completeness remains unverified; source-by-source auctioneer/year inventories, the remaining 491 incomplete states, 58 current failures and directory reconciliation still require work.


## Checkpoint: Edward Mellor overlaid PDF revision recovery

- Seven retained 2016/17 Edward Mellor result PDFs contained two text revisions overlaid on individual pages. Layout extraction had fused adjacent labels into false identities such as `2425`, `3739` and `4443`. Raw reading order now separates monotonic revision runs, and a page-boundary sequence check selects the one revision that continues through the surrounding pages without inventing an absent lot.
- A versioned parser refresh replaced the same source shard explicitly. The normal preservation default remains unchanged; eleven obsolete fused-label artifacts were removed instead of being silently restored by additive banking.
- The seven repaired result sheets now reconcile to 521 evidenced rows, up from 392. This recovered 129 dated address rows while removing eleven false address rows: a net gain of **118 dated address appearances**. There were no partial or undated additions.
- Edward Mellor's retained PDF corpus now contains **4,051 appearances**. Forty-eight of 55 discovered result PDFs are complete; five remain incomplete on explicit numbering gaps (11 December 2013, 4 February 2014, 19 March 2014, 30 April 2014 and 27 April 2016), and two retained links remain terminal source blockers. No missing row was synthesised.
- The published database verifies **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots** and **4,202 undated appearances**. Complete catalogue states increased from 2,007 to **2,014**; incomplete states fell from 491 to **484**; current fetch/parse failures fell from 58 to **50**.
- The focused and corpus tests pass. Workflow run `40210956286` passed collection, banking, database rebuild, packaging, source-register reconciliation, checkpoint publication and artifact upload. Artifact `12605741293` is 301,365,642 bytes with SHA-256 `f83176c32be5083b78537303fb5a334be4b6355ca2fdb05454aa8782b217f347`.

National completeness remains unverified: 484 incomplete catalogue states, 50 current source failures, 505 unlinked directory entries and uncovered operator/year inventories remain.

## Checkpoint: Pugh hybrid list/grid archive reconciliation

- Pugh's retained public property-search archive publishes **7,161 source rows**. The primary list endpoint supplied 6,940 rows before its historical boundary became unreliable; the saved fallback grid supplies **221 rows** covering normal pages 348–359.
- The previous checkpoint added the fallback grid total to every successfully fetched list page, including page 355, and therefore reported 7,181 reconciled rows. The collector now excludes any list page proved to fall inside the grid-covered interval. The exact equation is **6,940 non-overlapping list rows + 221 grid rows = 7,161 published rows**.
- The source checkpoint now records `published_rows_reconciled: 7161`, `source_rows_reconciled_complete: true`, `archive_pagination_complete: true`, no pagination failures, and **6,891 canonical source-shard rows**. The corpus retains **6,893 Pugh appearances** after existing separately evidenced records are included.
- **57 undated Pugh appearances** remain explicit partial evidence because their current detail URLs no longer expose an exact auction date; 56 return pages without the required identity/date evidence and one redirects to a 404. These are detail-enrichment blockers, not missing archive rows, and their dates remain null.
- This repair changes reconciliation state only. Corpus totals remain **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots**, and **4,202 undated appearances**. Catalogue metrics remain 2,014 complete, 484 incomplete or unreconciled, and 50 current fetch/parse failures.
- Repairs `b3a954ce2c029a5ee965ee532b0a75a6b4001a76` and `02969b3cf7d67dbce83f2d0a55a10696a1f9299f`, followed by generated checkpoint `e7b6f1dbfa7d78564619b1509ec1a1c6e5ef8993`, passed focused Pugh regression tests, corpus tests, source banking, database rebuilding, packaging, register reconciliation, checkpoint publication and artifact retention in workflow run `40216671321`.
- Artifact `12608286589` is 270,368,605 bytes with SHA-256 `fd1fe0072805dd6fec01ea2a811c58ec19d34ac666688d3c653fc6d9edebbd76`.

National completeness remains unverified: 484 incomplete catalogue states, 50 current source failures, 505 unlinked directory entries and uncovered source/operator/year inventories remain.



## Checkpoint: Symonds & Sampson retained-state classification

- The retained first-party corpus remains **227 property appearances**: **139 address records** and **88 partial lots**. Of these, **89 rows** carry exact auction dates across 31 dated event groups and **138 remain undated**; no values were inferred and no lot totals changed.
- All 208 URLs currently exposed by the saved official sitemap are banked, with 19 additional retained property pages no longer present in that sitemap. This proves completeness only for the saved/current sitemap inventory, not for the original event denominators or twenty-year history.
- The 31 dated event states previously stored the unavailable original-event denominator as an item in `errors`. The collector now records `source_rows_complete: true`, `denominator_reconciled: false`, a structured `original_event_denominator_unavailable` note, and an empty error list. Every one of the 31 events remains explicitly incomplete; none was promoted to catalogue-complete.
- The official sitemap returned zero property URLs during the first focused retry. A saved-row reconciliation mode now updates these state files without relying on the live sitemap or rewriting canonical appearances. The ordinary collector retains the same classification for future successful source refreshes.
- Repairs `0aa965f9654030a841a7705a74123d882ae22a5e` and `96c9e652492f168f22d13dda232e7d421db9ef43`, followed by generated checkpoint `73a61441ef9d74bf2f632f2088c6982e7a8c9f9c`, passed the focused Symonds & Sampson step, collector/workflow tests, banking, database rebuild, packaging, source-register reconciliation and checkpoint publication in workflow run `40220867932`.
- The published corpus remains **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots**, and **4,202 undated appearances**. Catalogue states remain **2,014 complete** and **484 incomplete or unreconciled**. Genuine current fetch/parse failures fall from 50 to **19** after removing the 31 denominator-availability limitations from that failure metric.
- Artifact `12609695088` is 301,081,647 bytes with SHA-256 `8af507b55489f682e6f6241467b227fc9d6f985638b8a6f3071ce3e3f3a60ed8`.

National completeness remains unverified: 484 incomplete catalogue states, 19 current source failures, 505 unlinked directory entries and uncovered source/operator/year inventories remain.


## Checkpoint: retained online-result denominator classification

- Five Auction House regional collectors and Town & Country were complete for every retained paginated first-party result row, but their saved states treated the unavailable original event denominator as a fetch/parse error. The six collectors now preserve that distinction on future runs, and an idempotent saved-state migration repaired the existing checkpoints without refetching or rewriting appearances.
- The repaired inventories contain **5,993 appearances**: **5,992 address records** and **1 partial lot**. Pagination is complete with no fetch failures. Every aggregate state remains `catalogue_complete: false`, `denominator_reconciled: false`; no original auction denominator was inferred.
- The covered retained ranges are Auction House East Anglia from 2 March 2018, South Yorkshire from 15 November 2018, North East from 18 October 2018, North West and South West from 24 January 2019, and Town & Country from 21 February 2022. These are retained row ranges, not claims of complete twenty-year operator coverage.
- Repair `e3e299fe9d378aa6bfc98ca43641894e06593201`, followed by generated checkpoint `80a39311551ce1be969f95458bf0538289ca430d`, passed focused migration tests, collector/workflow tests, banking, database rebuild, packaging, source-register reconciliation, publication and artifact retention in workflow run `40221610811`.
- Corpus totals remain **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots**, and **4,202 undated appearances**. Catalogue states remain **2,014 complete** and **484 incomplete or unreconciled**. Current fetch/parse failures fall from 19 to **13**; the remaining failures are three Cottons numbering gaps, five SDL pages without exact dates and five Edward Mellor numbering gaps.
- Artifact `12609995762` is 268,161,395 bytes with SHA-256 `717ee11675ad8e6bbb17573c6684c0dd3cfadd4d5f5f6a5cf15a71288dd75fe0`.

National completeness remains unverified: 484 incomplete catalogue states, 13 current source failures, 505 unlinked directory entries and uncovered source/operator/year inventories remain.


## Checkpoint: SDL retired-catalogue blocker reconciliation

- Five retained SDL catalogue links had already been proved terminal: four now redirect to the first-party archive index and the April 2024 link redirects to SDL's current buy-property page. All five remain **incomplete**, with zero captured rows, unknown original denominators and no inferred auction date.
- Their saved states incorrectly retained the identity parser exception in `errors` even though the HTTP requests succeeded and the terminal redirect was the material condition. An idempotent collector migration now preserves each original exception inside structured `source_blocker` provenance while clearing the generic fetch/parse error field. Future terminal redirects use the same classification.
- No lot rows changed. The published corpus remains **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots**, and **4,202 undated appearances**. Catalogue states remain **2,014 complete** and **484 incomplete or unreconciled**. Genuine current fetch/parse failures fall from 13 to **8**; the remaining failures are three Cottons numbering gaps and five Edward Mellor numbering gaps.
- Repair `fc0b8a3b506fcb28c9a68ae32fa9922f310e550c`, followed by generated checkpoint `7f8d4caa7a6d003d965108038406309d6d13729f`, passed the focused SDL migration, full collector/workflow tests, source banking, database rebuild, packaging, source-register reconciliation, publication and artifact retention in workflow run `40224011749`.
- Artifact `12610309740` is 301,025,656 bytes with SHA-256 `c39eb8d36fa0834c9fbd5d95c54a71dccb1c2a48a3bd96684f1ae18e7d0de54d`.

National completeness remains unverified: 484 incomplete catalogue states, 8 current source failures, 505 unlinked directory entries and uncovered source/operator/year inventories remain.


## Checkpoint: Edward Mellor section-number reconciliation

- Four complete first-party result PDFs were falsely failing the contiguous-lot check because their printed commercial section ends at lot 33–36, followed by a standalone `RESIDENTIAL` heading and the first residential result at lot 40. The collector now recognises only the exact reserved interval immediately around that evidenced heading; it never creates rows for the unused labels.
- Reconciled sheets are 11 December 2013 (**86 address appearances; reserved 36–39**), 4 February 2014 (**87; reserved 34–39**), 19 March 2014 (**95; reserved 36–39**) and 30 April 2014 (**124; reserved 37–39**). All remain exact-dated, source-snapshotted appearances with published outcomes and prices preserved.
- The 27 April 2016 PDF contains lots 69 and 71 with no printed lot 70 or section boundary. It therefore remains incomplete with lot 70 as a genuine unresolved numbering gap. No row, address, outcome or price was inferred.
- Edward Mellor PDF holdings remain **4,051 appearances**. Complete retained result PDFs increase from 48 to **52 of 55**; one numbering-gap sheet and two terminal source blockers remain explicit.
- No lot rows changed. The published corpus remains **279,944 individual appearances**: **269,575 address records**, **10,369 partial lots**, and **4,202 undated appearances**. Catalogue states improve from 2,014 complete / 484 incomplete to **2,018 complete / 480 incomplete**; current fetch/parse failures fall from 8 to **4**.
- Repair `a37f9f0fdfc646ede86202399492b22f0398b85e`, followed by generated checkpoint `5c2b7f09d37e8e33bafb4f05fa3c72ead1e51eac`, passed parser tests, the focused PDF refresh, source banking, database rebuild, packaging, source-register reconciliation, publication and artifact retention in workflow run `40228539835`.
- Artifact `12611687799` is 301,371,970 bytes with SHA-256 `f9cd366fdbbcdf01ccaf9f964e64fc55e688eff908ab0f01fb801dc2818b6aa0`.

National completeness remains unverified: 480 incomplete catalogue states, four current source failures, 505 unlinked directory entries and uncovered source/operator/year inventories remain.


## 25 October — prioritise actual growth over repeated reconciliation

The owner explicitly rejected the recent rate of growth. The hourly research
automation has been updated to prioritise unbanked lots, accessible missing
source-years and uncovered genuine auctioneers. Reclassification of unavailable
archives is maintenance, not newly captured property evidence. Zero-growth runs
must leave a different concrete growth target rather than retry the same route.

The continuation runner now defers eight explicitly reconciled, zero-growth
rolling archives for six hours. Positive gains, missing summaries, incomplete
pagination, failed attempts and reported failures do not trigger this deferral.
This changes historical refresh frequency only; current-listing collectors are
unaffected. New collectors remain in the regular rotation.

### Dawsons — a previously unlinked operator now captured

- Official source: https://dawsonsproperty.co.uk/past-auctions.php
- Fourteen pages reconcile to the published 138 past auction properties.
- 138 separate addressed source listings retained; 53 carry explicit closing or
  auction dates between 9 November 2023 and 12 August 2026. 85 remain undated.
- This pass started with no Dawsons shard on main. The final continuation summary
  reports 128 newly added records because an earlier local page checkpoint had
  already saved ten; the net new source total is 138, not 148.
- Source labels all 138 Sold. Displayed prices are unlabelled: preserved as
  source_display_price, never silently promoted to guide or achieved prices.
- 135 source-typed residential records, one land record and two garages left
  unclassified. This is nationwide all-sector expansion, not an increase of
  138 in the commercial/mixed-use headline.
- HTML snapshots, original links, source hashes, modal descriptions and dates
  are retained. Source paging completeness is distinct from complete original
  auction catalogues; national completeness remains false.
- Collector is reusable, checkpoints every successful page, preserves older
  records, distinguishes repeat dates and only refreshes a reconciled rolling
  archive daily. Tests cover price ambiguity, date scope, carousel pagination,
  partial failure preservation, idempotency and refresh behaviour.

### Recovery opportunities and bounded probes

Hollis Morgan's current collector stops at 2015. Official annual pages link
2016–July 2022 to hosted FlippingBook catalogues (47 links across seven years).
The sampled hosted routes currently return upstream 502 in the collector
environment; a separate retrieval returned 404. No later catalogue lots have
been admitted. Later 2022–2026 archive links point to a shared rolling sold page,
so that page must not be assigned repeatedly to each historical month. Stop
repeating the failed hosted URLs until a materially different recovery route is
available. The original 2010–2015 collector is unchanged.

Venmore advertises eleven pages of historical auctions. The direct past-auctions
route returned 403 in this environment; no rows have been claimed. Do not spend
successive runs retrying that same route.

Next high-volume research priorities: accessible older Barnard Marcus catalogues
before the retained 2024–2026 sitemap; Clive Emson before the retained 2023–2026
archive; Pattinson beyond its limited 2026 holdings. For each, first establish a
working source route and a measured uncaptured-lot opportunity. If blocked, move
to another uncovered operator from the source register. Claims of thousands of
recoverable lots must wait for actual source evidence.

Validation before publication: 47 targeted continuation, collector, workflow and
corpus tests pass. Final database totals must be read from the generated workflow
checkpoint after this source batch is rebuilt, not inferred from catalogue counts.

Publication verified: workflow 40230267106 completed successfully. The generated
25 October 20:22:49 UTC checkpoint now contains 280,082 appearances (+138),
269,713 address records (+138), and 272,724 dated appearances in the preceding
20-year window (+53). Undated appearances are 4,287 (+85). The 20:23:11 source
register links Dawsons and reduces unlinked directory candidates from 505 to
504; this is not a verified national auctioneer denominator. No new verified
guide or sale prices were claimed from the unlabelled Dawsons amounts.


## 25 October 2026 — Clive Emson 2022 roundup-result recovery

- Specific growth opportunity: eight saved first-party Clive Emson roundup articles for February, March, May, June, July, September, November and December 2022 linked selected historical result lots that were absent from the banked corpus.
- Added a reusable article collector and repaired its handling of malformed legacy markup (whole articles nested inside one paragraph). Focused tests pass 20/20.
- Published 40 net new individual appearances across source auctions 231–238. All 40 retain exact auction/lot identities, article month, property description, sold outcome, achieved price, original lot URL and immutable article snapshot.
- Quality split: 0 newly dated address records; 40 partial lots; 40 undated at exact-day level; 0 future-dated records; 0 duplicate-derived gains. Unknown street addresses and exact auction days remain null.
- Sector split: 4 commercial, 6 mixed-use, 17 residential, 5 land and 8 unknown. The commercial/mixed-use subset is 10.
- Price evidence: 40 new achieved prices; 0 new guide prices. Because the exact auction day is not published in these articles, the rows remain excluded from exact-date twenty-year totals even though all eight source articles evidence 2022 auction months.
- Current corpus after publication: 280,122 appearances, 269,713 address records and 10,409 partial lots; 4,327 appearances are undated.
- Terminal route evidence: the old catalogue containers and every article-linked lot-detail URL now redirect to generic region/current pages. Those redirects are recorded; do not repeat this route unless a materially different recovery source appears. Article snapshots remain the admissible evidence.
- National completeness remains false. The next concrete growth target is Barnard Marcus pre-2024 official/saved source-corpus lot recovery, beginning with unbanked exact detail identities rather than another Clive Emson redirect probe.

Implementation: [article fallback](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/cf612c88c09bcb0b60c8e830e0125e95aed94c0d), [malformed-markup repair](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/61334ebdd6907ba06d357940771aadab9a91650b), [settled-price repair](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/d293d7c9ff521b1592b645cae211f68690c878ac), [published checkpoint](https://github.com/garethburke5/Commercial-Auction-Sniper/commit/4cfbc7a6f08833c2327f0bc9822ab2472107aeb0), and [verification workflow](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/40238907788).


## 25 October 2026 — saved `records` lot recovery

- The saved-source audit found 94 evidence-bearing property rows under the legacy
  generic `records` array, which the permanent banker did not read. Exact
  canonical URL and date/address/lot reconciliation excluded 58 overlaps before
  growth was claimed.
- Banked 36 net new appearances: 34 address records and two partial lots. Thirty
  have exact dates and 28 are dated address records inside the preceding
  20-year window; six remain undated and none are future-dated.
- Sector split: 18 commercial, nine mixed-use, five land, one residential and
  three unknown. The commercial/mixed-use subset is 27.
- Price evidence: 25 new dated guide prices and 18 new dated sale prices. Two
  previously banked undated Acuitus rows also gained explicit sale prices from
  the saved legacy field. No new auctioneer/year pair was claimed: the recovery
  deepens already represented Allsop, Clive Emson and Savills years.
- The reusable importer now admits only explicit lot/property record types (or
  untyped rows with an address and lot number), excludes auction manifests,
  strips tracking queries for URL comparison, and preserves legacy
  `result_price` and `rent_pa` fields. Focused corpus tests pass 24/24.
- Rebuilt database totals are 280,158 appearances, 269,747 address records and
  10,411 partial lots. The exact-date 20-year window contains 272,754
  appearances, 96,256 guide prices and 104,984 sale prices. Undated appearances
  are 4,333; future-dated appearances remain 28. National completeness remains
  false.
- The removed Barnard Marcus September 2023 route remains a terminal 404 with no
  retained first-party lot identities. Do not retry it without a new source.
  Next growth target: audit other saved JSON array shapes and failed checkpoint
  artifacts for property rows, then move to a different accessible older source.


## 26 October 2026 — Future Property Auctions archive expansion

- Continued the productive first-party BidJS archive rather than repeating a
  blocked source. Banked **5,760 net new distinct appearances** across 2019,
  2020 and 2021, all with exact closing dates, addresses, original property
  links and immutable sanitised source snapshots.
- Quality split: 5,760 dated address records inside the preceding 20-year
  window; zero partial, undated or future-dated additions; zero duplicate
  appearance IDs. No new auctioneer/year pair was claimed because all three
  years were already represented.
- Sector split: 1,545 commercial, 2,203 mixed-use, 1,862 residential, 148 land
  and two unknown. The commercial/mixed-use subset is **3,748**.
- Price evidence: 611 new achieved prices and no new guide or rent values. The
  source does not publish a distinct guide field in these archived payloads, so
  bid values were not promoted to guides.
- Repaired the collector's too-narrow test-title filter. Five explicit test
  catalogues are now excluded, including three `Test Webcast Auction` payloads
  containing 55 non-production rows. The newly retrieved test payloads and
  states were removed before publication; they are not counted as properties
  or catalogues.
- The 42 newly recovered catalogues are stored as independently publishable
  normalized shards alongside their immutable source snapshots. The collector
  now reads the legacy aggregate plus catalogue shards and banks rows before
  marking a catalogue complete, avoiding repeated rewrites of a monolithic
  source file. Rebuildable database publications now use verified 8 MiB parts;
  older 32 MiB manifests remain readable.
- Future Property Auctions now retains **75,845** appearances and reconciles
  **228 of 229** genuine archived catalogues. One October 2019 catalogue
  endpoint returned transient HTTP 503 after bounded retries and remains pending.
- Rebuilt SQLite passed integrity checking at **291,419 appearances**:
  281,008 address records and 10,411 partial lots. The exact-date 20-year
  window contains 284,015 appearances, 96,256 guide prices and 105,988 sale
  prices. Undated appearances remain 4,333 and future-dated appearances 28.
- Next target: retry only the remaining transient 2019 endpoint after cooldown, then
  resume the saved-source array/checkpoint inventory. National completeness
  remains false.

## 26 October 2026 — Future Property Auctions archive completion

- The previously transient October 2019 endpoint recovered after cooldown. Its
  complete first-party BidJS payload reconciles 36 distinct listing UUIDs to 36
  banked appearance rows and an immutable sanitised snapshot.
- All 36 additions are address records dated 10 October 2019, inside the
  preceding 20-year window. No partial, undated, future-dated or duplicate
  records were added.
- Sector split: five commercial, nine mixed-use, 18 residential and four land.
  The commercial/mixed-use subset is 14.
- Three sold rows contribute actual achieved-price evidence. No guide or rent
  values were inferred from the payload.
- Future Property Auctions now retains 75,881 appearances and all 229 genuine
  archived catalogues reconcile. The five explicit test catalogues remain
  excluded.
- No new source-year pair is claimed because Future Property Auctions 2019 was
  already represented. National completeness remains false.
- Next concrete target: validate four saved Savills 2016-2017 lot clues that
  evidence actual dated auction appearances but lack lot numbers, while
  excluding the conditional Edbrooke listing unless a confirming result source
  is found. If identities remain insufficient, move to a different accessible
  older catalogue route rather than weakening admission rules.

## 26 October 2026 — Savills 2016–2017 saved-clue reconciliation

- Reconciled four previously saved property-level clues to actual dated Savills
  appearances: the sold Fulham Palace Road garage/development site on 9 May
  2016 and three development properties offered on 29 March 2017. Exact lot
  numbers remain unknown and are null.
- Gross additions are four dated address records. One earlier 42 High Street,
  Ewell row was removed because its source said only that it *would* be placed
  in the auction if not sold prior; there is no surviving confirmation that it
  appeared. Net growth is therefore **three appearances and three address
  records**, all inside the preceding 20-year window.
- The four admitted rows add four distinct guide prices and one achieved sale
  price. One new row is mixed-use; removing the unconfirmed Ewell commercial
  row makes the net commercial/mixed-use change zero. No rent evidence or new
  auctioneer/year pair was added.
- Two conditional leads (Edbrooke Road and Ewell) remain source clues rather
  than appearances. The Chelsea garage clue also remains excluded because the
  saved artifact lacks an exact address and original URL. No speculative lot
  identity was created.
- Added a reusable admission guard for conditional pre-auction marketing while
  preserving explicit sold-prior outcomes. The historical corpus suite passes
  26/26 tests and the rebuilt SQLite integrity check passes at 291,458 retained
  appearances: 281,047 address records and 10,411 partial lots. The exact-date
  20-year window contains 284,054 appearances, 96,260 guide prices and 105,992
  sale prices; 4,333 records remain undated and 28 future-dated.
- Next concrete target: reconcile the eight older saved `lot_partial`
  `source_records` in the Allsop July 2011 and Savills May 2008, May 2009 and
  March 2010 artifacts against existing shards, banking only non-overlaps and
  keeping unavailable exact dates and lot numbers null. National completeness
  remains false.

## 26 October 2026 — older Allsop/Savills `source_records` reconciliation

- Reconciled all eight saved `lot_partial` rows in the Allsop July 2011 and
  Savills May 2008, May 2009 and March 2010 artifacts against the permanent
  appearance shards.
- Six rows were already banked from overlapping source captures and were not
  counted again: three Allsop July 2011 investments, Savills' West Fareham
  office lot, the Eastbourne Reef 'n' Beef lot and the Fulham 2010 investment.
- Banked two genuinely absent Savills appearances: the mixed-use former surgery
  in Hurlingham Road reported sold in May 2008, and the 56/58 Dale Street and
  3 China Lane commercial/development site reported sold in May 2009.
- Net growth is **two appearances**: one address record and one partial lot.
  Both retain published auction months but have null exact days and lot numbers,
  so exact-date twenty-year coverage and newly dated address counts do not
  change. Both are commercial/mixed-use.
- The new rows add one guide price and two achieved sale prices. No rent value,
  future-dated row, duplicate appearance or new source-year pair is claimed.
- The unrelated live-board publication after the prior checkpoint had replaced
  `continuation_collection.json` with invalid binary content. The last valid
  historical continuation state is restored and advanced here so subsequent
  scheduled banking is not blocked.
- Next concrete growth target: inspect remaining saved non-standard arrays and
  checkpoint artifacts for unbanked property rows, beginning with evidence that
  has stable property descriptions plus source URLs rather than another probe
  of these six reconciled overlaps. National completeness remains false.

## 26 October 2026 — Symonds & Sampson event-archive recovery

- The sitemap-only collector retained 227 current property pages, but the
  first-party past-events index still exposed four pages and 42 dated event
  pages from 21 April 2023 through 23 October 2026. Those pages contain 967
  individual property cards.
- A new event-aware collector banks exact event/listing identities and retains
  the same listing again when it was genuinely reoffered on a different date.
  It excluded 65 exact listing/date overlaps with the canonical sitemap shard
  and found no duplicate event/listing/date pair.
- Net growth is **902 appearances**: 544 dated address records and 358 dated
  partial lots, all inside the preceding 20-year window. There are no undated
  or future-dated additions.
- Sector split: 379 residential, 361 land, 160 unknown and two commercial; the
  commercial/mixed-use subset is two. The saved cards add 670 guide prices and
  517 achieved sale prices. No rent evidence or new auctioneer/year pair is
  claimed because Symonds & Sampson 2023-2026 was already represented.
- All 42 event pages reconcile to their visible source rows, with immutable
  first-party index/event snapshots. Focused tests pass and the rebuilt SQLite
  integrity check is `ok` at 292,362 appearances: 281,592 address records and
  10,770 partial lots. The exact-date 20-year window contains 284,956
  appearances, 96,930 guide prices and 106,509 sale prices; 4,335 records
  remain undated and 28 future-dated.
- Next concrete growth target: recover Symonds & Sampson events before April
  2023 from surviving first-party result pages, article-linked catalogues or
  PDF snapshots. If no property-level route survives, move to an uncovered
  operator instead of refreshing this reconciled event archive. National
  completeness remains false.

## 26 October 2026 — 247 Property Auctions Bamboo archive

- The bounded pre-April 2023 Symonds & Sampson recovery found the first-party
  annual-results index and its four 2019–2022 PDF targets. All four current CDN
  targets return HTTP 404, exact-URL archive lookups expose no saved PDF
  binary, and exact UUID searches found no alternate copy. This route is now a
  recorded blocker and was not probed again after the bounded check.
- Moved to the previously uncovered genuine operator 247 Property Auctions.
  Its public Bamboo white-label archive advertises 263 listings across 14
  pages. All 263 index rows and all 263 stable-ID detail payloads reconcile,
  and immutable source snapshots retain both the page arrays and detail JSON.
- Net growth is **263 appearances and 263 address records**. Of these, 240 are
  exact-dated historical rows inside the preceding 20-year window, 22 are
  explicitly future-dated and one has no published close date and remains
  null/undated. No partial lot or duplicate stable ID was admitted.
- The 240 historical rows cover six newly represented operator/source-years,
  2021–2026. The full retained set comprises 166 residential, 70 mixed-use,
  11 commercial, eight land and eight unknown rows; the commercial/mixed-use
  subset is 81.
- All 263 rows retain published guide prices. Exactly 208 ended listings expose
  a positive highest bid together with an explicit `isReserveMet: true` flag,
  so 208 achieved sale prices are banked. Unmet-reserve bids remain unknown
  outcomes with null sale prices rather than being inferred as sales.
- Added a reusable Bamboo white-label collector plus tests for structured
  payload extraction, stable identity, exact close dates, reserve-aware sale
  evidence and null preservation for undated rows. The focused suite passes
  4/4 tests.
- The rebuilt SQLite integrity check is `ok` at **292,625 appearances**:
  281,855 address records and 10,770 partial lots. Exact-date twenty-year
  coverage is 285,196 appearances, 97,170 guide prices and 106,717 sale prices.
  Undated appearances are 4,336 and future-dated appearances are 50.
- Next concrete growth target: reconcile another genuinely uncovered UK
  Bamboo white-label operator, identify its first-party host, and apply this
  denominator/detail collector before returning to any blocked archive. Start
  with the uncovered Abode Auctions/AffordaBid/Agents Property Auction entries,
  accepting only a host whose displayed trading name matches the directory
  operator. National completeness remains false.

## 26 October 2026 — Landwood Property Auctions EIG archive

- Moved directly from the completed First for Auctions grid to the largest
  uncovered compatible EIG white-label found in the source register. Landwood
  Property Auctions had zero linked corpus records but publishes a first-party
  retained archive with an explicit 2,721-lot denominator.
- All 55 pages reconcile exactly to 2,721 distinct stable EIG lot identities.
  Every row has an address and exact individual lot end date between 22 March
  2018 and 21 October 2026; there are no partial, undated, future-dated or
  duplicate-derived additions.
- Net growth is **2,721 appearances and 2,721 dated address records** inside the
  preceding 20-year window. The sector split is 2,360 residential, 155
  mixed-use, 81 commercial, 37 land and 88 unknown; the evidenced
  commercial/mixed-use subset is 236.
- The archive adds 1,029 achieved sale prices and no index guide or rent
  values. Published sold, sold-prior, sold-after, unsold, withdrawn and
  postponed outcomes remain distinct. Nine operator-years, 2018–2026, are
  newly represented.
- The shared EIG parser now recognises an explicit `Sale price` as achieved
  evidence even when the page omits the separate word `sold`, and preserves
  `Sale Agreed Prior` as sold-prior. These rules are regression tested and do
  not turn unsold asking amounts into sale prices.
- Next concrete growth target: SW Property Auctions' separate first-party
  retained grid, currently advertising 204 property rows while remaining
  unlinked to the corpus. If that denominator reconciles, continue through the
  smaller uncovered Boultons Harrisons and OPA Group EIG grids rather than
  refreshing Landwood. National completeness remains false.

## 26 October 2026 — SW Property Auctions retained catalogue recovery

- Recovered every retained property card from 21 first-party past-auction
  pages. The pages reconcile to **204 distinct stable EIG lot identities**.
  The archive's separate `lots offered` statistic totals 159; it is preserved
  as an outcome statistic and is not misused to discard the 45 additional
  retained available, withdrawn or postponed rows.
- Net growth is **204 appearances and 204 address records**, all individually
  dated inside the preceding 20-year window: nine in 2024, 105 in 2025 and 90
  in 2026. There are no partial, undated, future-dated or duplicate-derived
  additions.
- The retained set comprises 139 residential, 34 commercial, 30 mixed-use and
  one land appearance. The commercial/mixed-use subset is 64.
- First-party detail pages add 203 guide prices, 76 achieved sale prices and
  113 explicit annual rents. Sold, sold-prior, sold-after, available,
  postponed and withdrawn outcomes remain distinct; undisclosed results stay
  null. Original catalogue/detail URLs and immutable snapshots are retained.
- The reusable collector records the displayed property-row denominator
  separately from archive outcome statistics, reconciles all 21 catalogues,
  and defers unchanged completed refreshes for 24 hours. Focused and workflow
  regression suites pass 57/57 tests.
- The rebuilt SQLite integrity check is `ok` at **296,962 appearances**:
  286,192 address records and 10,770 partial lots. Exact-date twenty-year
  coverage is 289,492 appearances, with 97,373 guide prices and 108,905 sale
  prices. Undated appearances remain 4,371 and future-dated appearances remain
  56. National completeness remains false.
- Next concrete growth target: collect the uncovered Boultons Harrisons
  first-party EIG grid (currently 62 retained property rows), then OPA Group's
  51-row grid. If either denominator fails to reconcile, record the specific
  gap and move to the other source rather than repeating a zero-growth probe.

## 26 October 2026 — Boultons Harrisons and OPA retained-grid recovery

- Added a reusable collector for flat, paginated EIG white-label result grids
  and applied it to both outstanding targets. Boultons Harrisons reconciles as
  50 + 12 rows; Online Property Auction Group reconciles as 50 + 1. All 113
  rows have distinct stable EIG lot UUIDs and first-party detail snapshots.
- Net growth is **113 address appearances** with no partial, undated or
  duplicate-derived records. Of these, 112 are dated within the preceding
  20-year window and one OPA withdrawal remains correctly future-dated to its
  published scheduled auction date of 28 October 2026.
- The retained set contains 22 commercial and eight mixed-use appearances
  (30 combined), 67 residential, 15 land and one unknown. Asset-sector rules
  prefer the property being sold over speculative alternative-use wording in
  descriptions.
- First-party detail pages add **113 guide prices**, while the result grids add
  **78 achieved prices**; 16 explicit annual rents are also retained. Sold,
  sold-prior, sold-after, unsold, withdrawn and postponed outcomes remain
  distinct, and non-sale amounts never become achieved prices.
- Six operator-year pairs are newly represented: Boultons Harrisons in 2025
  and 2026, plus OPA in 2023, 2024, 2025 and 2026. The completion claim covers
  every row in the surviving first-party grids, not deleted earlier material.
- Next concrete growth target: use this tested collector against another
  genuine uncovered EIG white-label operator only after resolving its
  first-party host and displayed trading name; otherwise recover an older
  property-level Boultons/OPA source rather than refreshing these complete
  grids. National completeness remains false.
