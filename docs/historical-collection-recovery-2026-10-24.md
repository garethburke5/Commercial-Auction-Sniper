Warning: truncated output (original token count: 40605)
Total output lines: 1939

Warning: truncated output (original token count: 41413)
Total output lines: 1985

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
…605 tokens truncated…y represented.
- The rebuilt corpus contains **304,533 appearances**, **293,762 addresses**,
  **10,771 partial records** and **296,886 dated appearances inside the current
  20-year window**, including **101,231 guide-price records** and **111,446
  achieved-price records**. Undated remains 4,395 and future-dated remains 209.
  Focused collection, overlap reconciliation, database rebuild, packaging,
  checkpoint publication and artifact retention all succeeded.
- The preceding continuation-file encoding fault was repaired from the last
  valid blob before this collector ran; the restored JSON was validated and no
  captured records or database evidence were discarded.
- **Next concrete growth target:** event
  `https://online.auctionhouse.co.uk/past-auctions/75000`, dated 11 November
  2025. Its first-party page exposes a substantial individual result inventory
  with numbered lots through Lot 100 and explicit outcomes. Reconcile its exact
  card denominator before claiming growth, require every detail page and apply
  the same strict date/address overlap audit. National completeness remains
  false.

## 27 October 2026 — Auction House Online May event retrieval blocker

- Event `69595` publishes 59 individual first-party property cards, but five
  requests to its standard archive route and five to the distinct explicit
  all-results route each ended in a 120-second read timeout before the index
  arrived. No inferred, directory-level or catalogue-container rows were
  admitted.
- Both bounded runs preserved their checkpoints, completed the source-corpus
  bank and database rebuild, and confirmed zero new appearances, dated,
  partial, undated or future rows, commercial/mixed-use additions, guide or
  sale prices, rents, duplicates or source-years. Corpus totals remain 304,492
  appearances, 293,721 addresses, 10,771 partial records and 296,845 dated
  appearances within 20 years, including 101,190 guides and 111,445 sale
  prices.
- Next target is event `https://online.auctionhouse.co.uk/past-auctions/70923`,
  with 92 individual cards dated 19 August 2025. Event 69595 will not be
  retried until its upstream response changes or a genuinely new retrieval
  route appears. National completeness remains false.

## 26 October 2026 — Robinson & Hall 2021 article and results-image recovery

- Recovered **37 additional individual address appearances** from two surviving
  first-party Robinson & Hall sources without refreshing the completed
  2024–2026 EIG sheets. The 17 June 2021 article retains 20 linked rows with
  stable EIG LotIDs; although its headline auction denominator is ten offered
  lots, the additional withdrawn/non-offered rows remain distinct appearances
  and are reported separately rather than discarded.
- The April 2021 article publishes a first-party results image containing 17
  address rows. Because neither the article nor image publishes an exact event
  day, all 17 retain `auction_date: null`, `source_month: 2021-04` and
  `date_precision: month`; no date was inferred. The immutable source image
  snapshot is admitted only when its SHA-256 matches
  `c9a3de874f1fcae2f6b0d170e1cb8e6d9b039b5d57d72801a64f756cde6215bd`.
- Net growth is **37 appearances and 37 address records**: 20 newly exact-dated
  records inside the preceding 20-year window and 17 month-only/undated
  records. There are no partial, future-dated or duplicate-derived additions.
  The newly covered operator-year is 2021; the commercial/mixed-use subset is
  zero under the evidence-based sector classifier.
- Published evidence adds **20 achieved sale prices**: six from the June table
  and 14 from the April image. Two April sold-prior rows have undisclosed
  prices and remain null; the April unsold row's £159,000 last bid is preserved
  as `reported_bid_reached`, never as an achieved price. No guide-price or
  rent evidence was published.
- The rebuilt and packaged corpus contains **297,783 appearances**: 287,013
  address records and 10,770 partial lots. Exact-date twenty-year coverage is
  290,272 appearances, with 97,715 guide prices and 109,328 sale prices. The
  Robinson & Hall retained set now totals 452 appearances across 2021 and
  2024–2026.
- Next concrete growth target: find and recover the **February 2021 Robinson &
  Hall property-level results** implied by the April article's combined
  February/April 38-lot statement (the April image accounts for 17 rows, leaving
  a potential February component). Admit rows only from first-party article,
  table or results-image evidence with an explicit date or month. If that
  property-level source is unavailable, move to Robinson & Hall's 2022/2023
  result articles or a different uncovered operator rather than re-probing the
  completed 2024–2026 sheets. National completeness remains false.

## 26 October 2026 — Robinson & Hall 2023 results-image recovery

- The persisted February 2021 target did not expose a complete first-party
  result sheet through a new route. Rather than re-probing it, collection moved
  to two substantial uncaptured first-party result images found through the
  same WordPress/API archive: **19 rows from 15 June 2023** and **24 rows from
  3 August 2023**.
- Both event dates are independently published in Robinson & Hall's first-party
  February 2023 catalogue. The collector verifies the catalogue PDF, both
  result images and their article references by SHA-256 before admitting the
  checked transcriptions. Completed 2021 article sources and the 2024–2026 EIG
  sheets are not refreshed by this focused route.
- Net growth is **43 appearances and 43 address records**, all exact-dated in
  the preceding 20-year window. There are no partial, undated, future-dated or
  duplicate-derived additions. The newly covered Robinson & Hall source-year is
  2023; the strict address-wording classifier adds no commercial/mixed-use
  rows rather than inferring sectors from ambiguous addresses.
- Published evidence adds **31 achieved sale prices**. Unsold bids of £120,000,
  £320,000, £396,000 and £420,000 are retained as `reported_bid_reached`, not
  achieved prices. No guide-price or rent evidence is present in these result
  images.
- The June article explicitly reports 17 offered lots while its image preserves
  19 rows, including two withdrawn-prior appearances. The August image
  preserves 24 rows, but its article does not publish an offered-lot
  denominator; that value remains null rather than being inferred from the 83%
  headline.
- The rebuilt and packaged corpus contains **297,826 appearances**: 287,056
  address records and 10,770 partial lots. Exact-date twenty-year coverage is
  290,315 appearances, with 97,715 guide prices and 109,359 sale prices.
  Robinson & Hall now contributes 495 appearances.
- Next concrete growth target: parse and bank individual lots from Robinson &
  Hall's surviving **2023 first-party catalogue PDFs**, beginning with February
  and April and then October/December. Preserve their event dates and guides,
  and exclude the already banked June/August result-image identities before
  claiming growth. If those catalogues cannot yield property rows, move to a
  different uncovered operator rather than refreshing completed Robinson &
  Hall sources. National completeness remains false.


## 26 October 2026 — Robinson & Hall 2023 catalogue inventory recovery

- Banked **51 additional individual address appearances** from two complete,
  surviving first-party catalogue PDFs: 25 contiguous lots from 23 February
  2023 and 26 contiguous lots from 7 December 2023. Both PDFs are admitted
  only when their SHA-256 values match the checked source bytes, and immutable
  compressed source snapshots are stored with the rows.
- Net growth is **51 appearances and 51 address records**, all exact-dated in
  the preceding 20-year window. There are no partial, undated, future-dated or
  duplicate-derived additions. Robinson & Hall 2023 was already represented
  by June/August results, so no new operator-year is claimed; the newly
  reconciled source-date inventories are 2023-02-23 and 2023-12-07.
- The order-of-sale evidence adds **51 exact guide prices**, distinct from sale
  prices. It adds no achieved prices or rent values. Evidence-based catalogue
  types identify four commercial/mixed-use appearances; ambiguous
  redevelopment descriptions are not promoted to commercial.
- The initial publication checkpoint preserved the batch but failed database
  rebuild because the new auction metadata omitted the required
  `lots_captured` field. The field was added and the focused workflow then
  completed successfully; no captured record was discarded.
- The rebuilt corpus contains **297,877 appearances**: 287,107 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 290,366
  appearances, with 97,766 guide prices and 109,359 sale prices. Robinson &
  Hall now contributes 546 appearances.
- Next concrete growth target: traverse the confirmed first-party August 2023
  interactive catalogue at
  `https://interactive.property-world.co.uk/robinsonandhall_Aug23/catalogue.html`,
  reconcile its full lot inventory against the 24 already banked 3 August
  result rows, bank only catalogue lots absent from those results, and enrich
  exact matches with guides without creating new appearances. If the inventory
  contains no missing lots, preserve the guide enrichment and move to a
  different uncovered operator rather than re-probing the unavailable April
  and October URL patterns. National completeness remains false.

## 26 October 2026 — saved source-corpus reconciliation and duplicate repair

- The confirmed Robinson & Hall August 2023 interactive catalogue contains 23
  order-of-sale lots. All 23 reconcile to the already banked 3 August result
  appearances (the result image also contains Blue Barn, sold prior, which the
  catalogue omits), so no catalogue row is claimed as a new appearance. Its 23
  catalogue guides remain a separate enrichment target.
- Added a reusable importer for the previously unbanked
  `data/source_corpus/` root, including inheritance of auction-level dates and
  URLs, preservation of guide, achieved price and rent fields, immutable source
  snapshots, and explicit enrichment support. The focused suite passes all 27
  tests.
- Reconciled all 59 saved property-evidence rows without inflating the corpus.
  Thirty-three 2015 Allsop address rows collapse to 31 unique source rows and
  all 31 now match later canonical exact-date/address appearances. Of 25 AID986
  partials, two uniquely enrich existing 5 December 2016 appearances and the
  other 23 overlap the retained AID986 source. The one Savills row also overlaps
  retained evidence. The derived staging shards are now replaced, including
  empty tombstones, so a synced worktree cannot resurrect those duplicates.
- The AID986 reconciliation adds lot numbers 1 and 5 to their exact canonical
  appearances and adds one newly evidenced achieved price: **£260,000** for
  9 & 9A High Street, Princes Risborough. It does not create a second
  appearance or merge the related North Finchley legal interest.
- The concurrent bounded collector banked **7 genuine new address
  appearances**: one Auction House East Anglia, three First for Auctions, one
  The Auction Company and two Town & Country Property Auctions. Three are
  dated 26 October 2026 inside the current twenty-year window; four are
  explicitly future-dated (29 October or 10 November) and remain outside that
  coverage count. Outcomes are six sold-prior and one postponed. Four rows are
  residential and three remain unknown; the commercial/mixed-use subset is
  zero. No new operator-year is claimed.
- Those seven appearances add **two guide prices** (£220,000 current-date and
  £260,000 future-dated) and no achieved sale prices. Together with the AID986
  enrichment, this run therefore adds two genuine guide observations and one
  genuine achieved-price observation.
- The integrity repair also removed **23 pre-existing overlapping appearances**
  (21 Allsop/Allsop Commercial 2010 rows and two Savills 2018 rows), in addition
  to removing the 31 newly staged Allsop duplicates. Consequently the database
  row total is honestly 16 lower than the pre-run baseline despite seven newly
  banked appearances: **297,861 appearances**, comprising **287,091 address
  records** and **10,770 partial lots**. Exact address groups rise by six to
  158,040. Exact-date twenty-year coverage is 290,346 appearances, with 97,746
  guide prices and 109,358 sale prices; undated appearances remain 4,388 and
  future-dated appearances rise by four to 84.
- Next concrete growth target: build a first-party Auction Works collector over
  `https://www.auctionworks.co.uk/search`, whose currently exposed search
  denominator is 644 individual results. Reconcile the operator and pagination,
  capture stable property URLs, dates, guides, published outcomes and achieved
  prices, and compare every exact identity against the corpus before claiming
  growth. Auction Works currently has no linked retained appearances, so this
  is a materially different, potentially high-yield route. The 23 Robinson &
  Hall August guide enrichments are secondary and must not be counted as new
  appearances. National completeness remains false.

## 26 October 2026 — Auction Works complete retained-grid expansion

- Reconciled the first-party Auction Works search archive exactly: **644**
  published results, **644** distinct stable lot UUIDs and page inventories of
  50 rows on each of the first 12 pages plus 44 on page 13. All 644 detail
  pages and immutable source snapshots were captured without recovery errors.
- Banked **644 net new address appearances**. Of these, **627** have exact dates
  inside the current 20-year window and **17** are explicitly future-dated.
  There are no partial, undated or duplicate-derived additions.
- Preserved outcomes separately: 525 sold, 92 unsold, 9 withdrawn, 1 postponed
  and 17 still unknown/open. The batch adds **496 achieved sale prices**, **6
  guide prices**, no rents, and 7 commercial/mixed-use appearances. Minimum
  opening bids and a current bid remain distinct evidence and are not promoted
  to guide or achieved prices.
- Auction Works now has source-year coverage for **2020 through 2026**. The
  rebuilt corpus contains **298,505 appearances**: 287,735 address records and
  10,770 partial lots. Exact-date twenty-year coverage is 290,973 appearances,
  with 97,747 guide prices and 109,854 sale prices. Database rebuild, packaging,
  source-register reconciliation and publication all completed successfully.
- Next concrete growth target: run the same denominator-reconciled collector
  against Bradley Hall's first-party archive at
  `https://auction.bradleyhall.co.uk/search`. A non-persisting validation run
  reconciled **75** UUIDs across pages of 50 and 25, with all 75 detail pages
  available. It projects 54 dated non-future address appearances, 21
  commercial/mixed-use records, 75 guides, 50 achieved prices, 11 rents and 21
  explicitly future-dated listings. The Bradley Hall source configuration and
  focused tests are prepared; do not count these records until the collector
  banks them and the rebuilt database verifies them. National completeness
  remains false.

## 26 October 2026 — Bradley Hall retained-grid expansion

- Reconciled Bradley Hall's complete surviving first-party search archive:
  **75** published rows, **75** distinct stable UUIDs and two pages containing
  50 and 25 rows. All 75 detail pages and immutable snapshots were captured
  without recovery failures.
- Banked **75 net new address appearances**. Fifty-four are exact-dated inside
  the current 20-year window and 21 are explicitly future-dated through 23
  November 2026. There are no partial, undated or duplicate-derived additions.
- The batch contains 17 mixed-use and four commercial appearances (21
  combined), 46 residential, seven land and one evidence-limited unknown.
  Published outcomes remain distinct: 32 sold, 21 sold-prior, one postponed
  and 21 current/unknown listings.
- Added **75 guide prices**, **50 achieved prices** and **11 annual rents**.
  The 2025 and 2026 Bradley Hall operator-years are newly represented.
- The rebuilt corpus contains **298,580 appearances**: 287,810 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,027
  appearances, with 97,801 guide-price records and 109,904 sale-price records.
  Rebuild, packaging, source reconciliation and checkpoint publication all
  completed successfully.
- Next concrete growth target: Clarke & Simpson's genuine first-party EIG
  archive at `https://clarke-simpson.eigonlineauctions.com/search`, currently
  exposing 167 rows and no counted Clarke & Simpson appearances. The reusable
  collector now accepts the platform's stable numeric identities as well as
  UUIDs; it must reconcile the live denominator and exclude shared-EIG identity
  overlaps before claiming growth. National completeness remains false.

## 26 October 2026 — Clarke & Simpson retained-grid expansion

- Reconciled the complete surviving first-party archive: **167** published
  rows, **167** distinct stable EIG identities and four pages containing 50,
  50, 50 and 17 rows. All 167 detail pages and immutable snapshots were
  captured without recovery failures.
- Banked **167 net new address appearances**. Of these, **160** have exact
  dates inside the current 20-year window and seven are explicitly
  future-dated through 18 November 2026. There are no partial, undated,
  overlapping or duplicate-derived additions.
- The batch contains 13 commercial and five mixed-use appearances (18
  combined), 127 residential and 22 land records. Published outcomes remain
  distinct: 92 sold, 15 sold-prior, eight sold-after, 40 unsold, two
  withdrawn, three postponed and seven current/unknown listings.
- Added **167 guide prices**, **92 achieved prices** and **17 annual rents**.
  Clarke & Simpson source-years 2021 through 2026 are newly represented.
- The rebuilt corpus contains **298,747 appearances**: 287,977 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,187
  appearances, with 97,961 guide-price records and 109,996 sale-price records.
  Collection, database rebuild, packaging and source publication succeeded.
- Repaired `continuation_collection.json` from its last valid Git object after
  a prior API write had committed a truncated display excerpt. That corruption
  caused this run's source-register reconciliation step to fail after the
  rebuilt records were already safe; the register is regenerated from the
  current progress and repaired continuation state in the follow-up checkpoint.
- Next concrete growth target: Higgins Drysdale National Property Auctions'
  independent first-party archive at
  `https://higginsdrysdale.eigonlineauctions.com/search`, currently exposing
  164 rows. Its reusable collector configuration and focused tests are
  prepared for the next isolated run. National completeness remains false.

## 26 October 2026 — Higgins Drysdale retained-grid expansion

- Reconciled the first-party grid's **164** published cards across pages of
  50, 50, 50 and 14. Of these, 163 are distinct dated auction-lot identities;
  the remaining card is explicitly headed “Property For Sale via Committed
  Offer” and is retained in the exclusion audit with its address, UUID and URL
  rather than misrepresented as an auction appearance.
- Banked **163 net new address appearances**. **162** are exact-dated inside
  the current 20-year window and one is explicitly future-dated (30 October
  2026). There are no partial, undated, overlapping or duplicate-derived
  additions.
- Added **163 guide prices** and **59 achieved prices**; no rent was published.
  The batch contains nine commercial and seven mixed-use appearances (16
  combined), 138 residential, six land and three evidence-limited unknowns.
  Higgins Drysdale source-years 2021 through 2026 are newly represented.
- Published outcomes remain distinct: 55 sold, 14 sold-prior, nine sold-after,
  38 unsold, 34 withdrawn, 11 postponed and two unknown. All 163 detail pages
  and immutable source snapshots were captured with no recovery failures.
- The rebuilt corpus contains **298,910 appearances**: 288,140 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,349
  appearances, with 98,123 guide-price records and 110,055 sale-price records.
  Collection, database rebuild, packaging, source-register reconciliation and
  protected publication completed successfully.
- Next concrete growth target: Brown&Co's independent first-party EIG archive
  at `https://brownandco.eigonlineauctions.com/search`, currently exposing 454
  rows. The corpus already holds 28 Brown&Co appearances from its rolling
  first-party result page, so the archive collector must exclude exact stable-ID
  overlaps before reporting net growth. National completeness remains false.

## 27 October 2026 — Brown&Co retained-grid expansion and identity reconciliation

- Reconciled **456** published auction-lot cards across ten first-party search
  pages and captured all 456 detail pages without recovery failures. The archive
  uses UUID identities while Brown&Co's older rolling page used numeric EIG IDs,
  so ID equality alone was not a valid overlap test.
- Exact full-address plus auction-date comparison identified **21** genuine
  identity migrations. Those appearances now retain both immutable evidence
  trails under the archive UUID; seven nonmatching legacy rows remain distinct.
  The final Brown&Co shard therefore contains **463** appearances, not the
  temporarily inflated 484 and not the overly conservative 456.
- Banked **435 net new address appearances** against the 28-row pre-archive
  corpus. **430** are exact-dated within the current 20-year window, five are
  explicitly future-dated, and none are partial or undated. Newly represented
  Brown&Co source-years are 2020 and 2022–2025; 2026 was already represented.
- Added **456 guide prices**, **392 net new achieved-price records** and five
  annual rents. The gain contains 20 commercial and four mixed-use appearances.
  Published outcomes remain separate: 412 sold, 25 sold-after, eight
  sold-prior, five unsold, six withdrawn, one postponed and six unknown.
- The rebuilt corpus contains **299,345 appearances**: 288,575 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,787
  appearances, with 98,581 guide-price records and 110,447 sale-price records.
  Collection, database rebuild, packaging, source-register reconciliation and
  publication completed successfully. National completeness remains false.
- Next concrete growth target: The Property Auction House, a genuine
  directory-listed Welsh operator with no retained corpus match. Its first-party
  archive at `https://thepropertyauctionhouse.eigonlineauctions.com/search`
  currently publishes **134** rows across three pages. Reconcile the live
  denominator, exclude non-auction committed-offer/online-sale cards, and bank
  only property appearances with stable identities and immutable evidence.

## 27 October 2026 — The Property Auction House retained-grid expansion

- Reconciled all **134** visible first-party cards across three pages. The
  source contains 127 distinct auction-lot identities and seven separately
  labelled committed-offer/online-sale cards. The latter retain their address,
  URL and stable UUID in the exclusion audit but are not counted as auction
  appearances.
- Banked **127 net new address appearances** with no partial, undated,
  overlapping or duplicate-derived additions. **112** are exact-dated inside
  the current 20-year window and 15 are explicitly future-dated through 10
  December 2026. Source-years 2022 through 2026 are newly represented.
- Added **127 guide prices**, **53 achieved prices** and two annual rents.
  The evidence-based sector split is 121 residential, four land and two
  commercial appearances; no row is promoted to mixed-use without explicit
  source wording. Outcomes remain distinct: 23 sold, 79 sold-prior, ten
  sold-after and 15 current/unknown future listings.
- All 127 detail pages and immutable snapshots were captured without recovery
  failures. The rebuilt corpus contains **299,472 appearances**: 288,702
  address records and 10,770 partial lots. Exact-date twenty-year coverage is
  291,899 appearances, with 98,693 guide-price records and 110,500 sale-price
  records. Tests, database rebuild, packaging, source-register reconciliation
  and protected publication completed successfully.
- Restored `continuation_collection.json` from the immediately preceding valid
  Git blob before collection after detecting a binary-corrupt API-written
  checkpoint; the focused JSON-validity test passed and no source batch was
  discarded.
- Next concrete growth target: verify that directory-listed **Property Auction
  Agent** is a genuine Swansea operator distinct from The Property Auction
  House, then collect its first-party EIG archive at
  `https://propertyauctionagent.eigonlineauctions.com/search`, currently
  exposing **66** cards across two pages and zero retained corpus appearances.
  If company or trading-name evidence shows an alias, merge attribution without
  claiming an additional operator. National completeness remains false.

## 27 October 2026 — Property Auction Agent retained-grid expansion

- Reconciled all **66** published rows in Property Auction Agent's surviving
  first-party EIG archive across two pages of 50 and 16. Every row has a
  distinct stable source identity; all 66 detail pages and immutable source
  snapshots were captured without recovery failures.
- The operator was reconciled before collection. **PROPERTY AUCTION AGENT LTD**
  (company 15163018, active, directed by Gemma Williams) is legally distinct
  from **THE PROPERTY AUCTION HOUSE LTD** (company 13597386, active, directed
  by Robert Leach). Julie Lawry's historic/director and current consultancy
  connections make the businesses related, but not aliases. The shared-EIG
  stable-ID guard nevertheless excludes any exact platform lot overlap.
- Banked **66 net new address appearances** with no partial, undated,
  overlapping or duplicate-derived additions. **61** are exact-dated inside
  the current 20-year window and five are explicitly future-dated through
  26 November 2026. Source-years 2023 through 2026 are newly represented.
- Added **66 guide prices**, **4 achieved prices** and one annual rent. The
  evidence-based sector split is 56 residential, five commercial, two
  mixed-use and three land appearances. Outcomes remain distinct: 55
  sold-prior, two sold, one postponed, three withdrawn and five current or
  otherwise unknown future listings.
- The rebuilt corpus contains **299,538 appearances**: 288,768 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,960
  appearances, with 98,754 guide-price records and 110,504 sale-price records.
  Focused tests, database rebuild, packaging, source-register reconciliation
  and protected source publication completed successfully.
- Next concrete growth target: **LOT9 Auction House Limited** (company
  12953855), a genuine operator rather than a Monopoly Buy Sell Rent alias.
  Its first-party archive at
  `https://lot9.eigonlineauctions.com/search` currently publishes **34**
  rows from 2022 through 2026 and has no retained corpus match. Reconcile the
  live denominator and shared EIG identities, preserve repeated offerings as
  separate appearances, and retain partner-agent wording as provenance rather
  than creating a second auctioneer. National completeness remains false.

## 27 October 2026 — LOT9 Auction House retained-grid expansion

- Reconciled all **34** published auction-lot cards on LOT9 Auction House's
  surviving first-party EIG archive. The one-page denominator, 34 distinct
  stable identities and all 34 detail pages reconcile exactly, with no
  malformed rows, non-auction exclusions, shared-platform overlaps or recovery
  failures.
- Banked **34 net new address appearances**, all exact-dated inside the current
  20-year window. There are no partial, undated, future-dated or
  duplicate-derived additions. LOT9 source-years 2022 through 2026 are newly
  represented.
- Added **27 guide prices** and **11 achieved prices**; no rent value was
  published. The evidence-based sector split is 31 residential, two mixed-use
  and one evidence-limited unknown. Outcomes remain distinct: two sold, 12
  sold-prior, two sold-after, six unsold, six withdrawn and six postponed.
- Reconciled the operator before counting coverage: **LOT9 AUCTION HOUSE
  LIMITED** (company 12953855) is the auctioneer. Monopoly Buy Sell Rent is
  retained as a partner agent in the source provenance and is not counted as a
  second auctioneer.
- The rebuilt corpus contains **299,572 appearances**: 288,802 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 291,994
  appearances, with 98,781 guide-price records and 110,515 sale-price records.
  The canonical shard contains 34 unique appearance IDs and 34 unique source
  IDs, every row retaining its original URL and immutable source evidence.
  Focused tests, database rebuild, packaging, source-register reconciliation
  and publication completed successfully.
- Next concrete growth target: **Auction North Limited** (company 10762287), a
  genuine directory-listed County Durham operator with no retained corpus
  match. Its first-party archive at
  `https://auction-north.eigonlineauctions.com/search` currently publishes
  **37** rows from 2020 through 2026. Reconcile the live denominator and shared
  EIG identities, retain Dynamic Property Group and other local partners as
  provenance rather than separate auctioneers, and bank dates, guides, achieved
  prices, rents, outcomes, original URLs and immutable snapshots. National
  completeness remains false.

## 27 October 2026 — Auction North retained-grid expansion and outcome repair

- Reconciled all **37** published auction-lot cards on Auction North's
  surviving first-party EIG archive. The one-page denominator, 37 distinct
  stable identities and all 37 detail pages reconcile exactly, with no
  malformed rows, non-auction exclusions, shared-platform overlaps or recovery
  failures.
- Banked **37 net new address appearances**, all exact-dated inside the current
  20-year window. There are no partial, undated, future-dated or
  duplicate-derived additions. Auction North source-years 2019 through 2026
  are newly represented.
- Added **28 guide prices**, **24 achieved prices** and **8 rent values**. The
  evidence-based sector split is 36 residential and one evidence-limited
  unknown; there are no commercial or mixed-use appearances. Outcomes remain
  distinct: 23 sold, three sold-prior, one sold-after, eight unsold and two
  withdrawn.
- Repaired the reusable EIG result parser after the first pass exposed
  `Sale Agreed`, `Sale Agreed Prior` and `Sale Agreed Post/After` as
  previously unmapped result phrases. Reprocessing the same 37 stable
  identities added 14 achieved-price values without inflating the appearance
  count. Monthly rent wording is now recognised and annualised while the
  published text remains preserved. All 39 focused tests pass.
- Reconciled the operator before counting coverage: **AUCTION NORTH LIMITED**
  (company 10762287) is the auctioneer. Dynamic Property Group and independent
  local property experts are retained as partner provenance and are not counted
  as additional auctioneers.
- The rebuilt corpus contains **299,609 appearances**: 288,839 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 292,031
  appearances, with 98,809 guide-price records and 110,539 sale-price records.
  Every retained row has its original URL and immutable source evidence.
  Focused collection, outcome repair, database rebuild, packaging,
  source-register reconciliation and protected publication completed
  successfully.
- Next concrete growth target: **Sage & Co Auctions Limited** (company
  13328873), a genuine Welsh operator with no retained corpus match. Its
  first-party archive at
  `https://sageandco.eigonlineauctions.com/search` currently exposes 17
  cards: 15 completed historical rows and two future-dated November 2026
  listings that must remain explicitly future-dated rather than being reported
  as historical growth. Reconcile all stable identities, preserve commercial,
  mixed-use and land evidence, and bank dates, guides, achieved prices, rents,
  outcomes, original URLs and immutable snapshots. National completeness
  remains false.

## 27 October 2026 — Sage & Co Auctions retained-grid expansion

- Reconciled all **17** published auction-lot cards in Sage & Co Auctions'
  surviving first-party EIG archive. The one-page denominator, 17 distinct
  stable identities and all 17 detail pages reconcile exactly, with no
  malformed rows, non-auction exclusions, shared-platform overlaps or recovery
  failures.
- Banked **17 net new address appearances** with no partial, undated or
  duplicate-derived additions. **15** are exact-dated inside the current
  20-year window and two are explicitly future-dated to 18 November 2026.
  Source-year 2026 is newly represented.
- Added **17 guide-price records** (15 within the current window), **4 achieved
  prices** and no published rent values. The evidence-based sector split is
  eight residential, three mixed-use, three land, one commercial and two
  evidence-limited unknown appearances. Outcomes remain distinct: two sold,
  three sold-prior, five unsold, three withdrawn, two postponed and two
  current/future unknown listings.
- Reconciled the operator before counting coverage: **SAGE & CO AUCTIONS
  LIMITED** (company 13328873) is the auctioneer. The company number appears on
  the first-party archive itself and agrees with the Companies House record.
- The rebuilt corpus contains **299,626 appearances**: 288,856 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 292,046
  appearances, with 98,824 guide-price records and 110,543 sale-price records.
  The canonical shard contains 17 unique appearance IDs and 17 unique source
  lot IDs; every row retains its original URL, grid evidence and detail
  evidence. Focused tests, database rebuild, packaging, source-register
  reconciliation and protected publication completed successfully.
- Next concrete growth target: reconcile directory-listed **Bowen** with the
  surviving **Bowen Son and Watson** trading name and its rebranded first-party
  site, then collect
  `https://bowensonandwatson.eigonlineauctions.com/search`. The archive
  currently exposes 24 stable cards: 22 completed rows spanning 2021, 2023 and
  2026 plus two future-dated November 2026 listings. It has zero retained
  corpus appearances. Preserve the trading-name history without counting an
  alias as a second operator, and bank individual dates, guides, achieved
  prices, rents, outcomes, original URLs and immutable snapshots. National
  completeness remains false.

## 27 October 2026 — Bowen / Bowen Son and Watson retained-grid expansion

- Reconciled all **24** published auction-lot cards in the surviving first-party
  Bowen Son and Watson EIG archive. The one-page denominator, 24 distinct
  stable identities and all 24 detail pages reconcile exactly, with no
  malformed rows, non-auction exclusions, shared-platform overlaps or recovery
  failures.
- Banked **24 net new address appearances** with no partial, undated or
  duplicate-derived additions. **22** are exact-dated inside the current
  20-year window and two are explicitly future-dated to 5 and 12 November
  2026. Bowen source-years 2020, 2021, 2023 and 2026 are newly represented.
- Added **12 guide-price records** (**10** inside the current window), **16
  achieved prices** and no published rent values. The evidence-based sector
  split is 18 residential, five land and one commercial appearance. Outcomes
  remain distinct: 16 sold, one sold-prior, two unsold, three withdrawn and
  two current/future unknown listings.
- Reconciled the auctioneer family before counting coverage. Current **Bowen**
  and historical **Bowen Son and Watson** are one operator/trading lineage;
  the archive's “Bowen Son and Watson with Kent Jones” wording and the 2019
  Kent Jones merger are retained as provenance, not counted as additional
  auctioneers. No unverified limited-company identity was invented.
- The rebuilt corpus contains **299,650 appearances**: 288,880 address records
  and 10,770 partial lots. Exact-date twenty-year coverage is 292,068
  appearances, with 98,834 guide-price records and 110,561 sale-price records.
  The canonical shard contains 24 unique appearance IDs and 24 unique source
  lot IDs; every row retains its original URL and immutable grid/detail source
  evidence. All **456** focused tests, database rebuild, packaging,
  source-register reconciliation and protected publication completed
  successfully.
- Next concrete growth target: directory-listed **Astleys**, which still has
  zero retained corpus appearances. Its first-party archive at
  `https://astleys.eigonlineauctions.com/search` currently exposes **26**
  completed cards spanning 2023 through 2026, with guide, outcome and achieved
  price evidence. Reconcile the Astleys trading/operator identity and any
  shared-EIG overlaps before adding it to the reusable retained-grid collector.
  National completeness remains false.

## 27 October 2026 — Astleys retained-grid expansion

- The focused Astleys collector banked **26 net-new individual property appearances** from the complete surviving first-party EIG grid: **26 address records**, **0 partial**, **0 undated**, **0 future-dated**, and **0 duplicate source appearances**.
- All 26 addresses have exact auction dates inside the current 20-year window, spanning **7 February 2023 to 20 March 2026** and adding source-years **2023, 2024, 2025 and 2026**.
- Sector evidence comprises 20 residential, 3 commercial, 1 land and 2 unknown appearances; the commercial/mixed-use increment is **3** (3 commercial, 0 mixed-use).
- Newly banked price evidence is **23 guide prices** and **15 achieved sale prices**; no rent values were published in these retained lots. Outcomes are 15 sold, 5 unsold, 4 withdrawn, 1 sold prior and 1 sold after.
- Operator reconciliation is explicit: Astleys is one Swansea operator under **ASTLEY SAMUEL LEEDER LTD (company 03129558)**. No branch, alias or shared-platform participant was counted as another auctioneer.
- The immutable evidence set contains 26 original lot URLs, 26 grid snapshots and 26 detail snapshots. Canonical verification found 26 unique appearance IDs and 26 unique source lot IDs.
- The rebuilt corpus now contains **299,676 appearances**, including **288,906 address records**, **10,770 partial records**, **292,094 exact-dated address records inside the current 20-year window**, **98,857 guide-price records** and **110,576 achieved-price records**. Undated remains 4,388 and future-dated remains 151.
- Collector and workflow verification passed **458 tests** (365 collector tests plus 93 workflow tests). National completeness remains false.
- Sarah Mains was rejected as the next target because its apparent 588-lot subdomain redirects to Auction Works, whose 644 retained appearances already cover the shared platform; treating it as a new operator would inflate growth.
- **Next growth target:** batch the accessible uncovered Opal Property retained grid (20 visible address cards, 2020-2023) with the Newlands Property retained grid (9 visible address cards), reconcile their legal operators and stable-ID overlaps, then bank only genuine net-new appearances. The former Star Property 16-card route currently returns 404 and is not the next collection route.


## 27 October 2026 — Opal Property and Newlands Property retained-grid expansion

- Reconciled both surviving first-party EIG grids: **20/20 Opal Property**
  cards and **9/9 Newlands Property** cards, each with distinct stable source
  identities and every detail page captured. The two first-party brands remain
  separate genuine directory entries; no branch, alias or shared-platform
  participant is counted as an extra auctioneer, and no unverified limited
  company identity was invented.
- Banked **29 net-new address appearances**, all exact-dated inside the current
  20-year window. There are no partial, undated, future-dated,
  duplicate-derived or non-auction-card additions. The new source-year pairs
  are Opal 2020–2023 and Newlands 2023–2026 (**8 auctioneer-year pairs**).
- Added **29 guide-price records**, **0 achieved prices** and **12 rent
  values**. The evidence-based sector split is 23 residential, three mixed-use,
  one commercial, one land and one evidence-limited unknown appearance; the
  commercial/mixed-use increment is **4**. Outcomes remain distinct: 11
  unsold, eight sold-prior, four sold-after and six withdrawn.
- Repaired a reusable source-route defect exposed by Newlands: its root URL is
  only a zero-delay meta-refresh landing page. The collector now requests the
  retained `/search` grid directly while preserving a zero-row response as a
  fatal reconciliation failure. **94 focused tests** pass.
- The rebuilt corpus contains **299,705 appearances**: **288,935 address
  records**, **10,770 partial records** and **292,123 exact-dated appearances
  inside the current 20-year window**, including **98,886 guide-price records**
  and **110,576 achieved-price records**. Every added row retains its original
  lot URL and immutable grid/detail source evidence. Database rebuild,
  packaging, source-register reconciliation and protected publication
  completed successfully.
- **Next concrete growth target:** collect Loveitts' substantial uncovered
  first-party archive at
  `https://www.loveitts.co.uk/auctions/past-auctions`. Its public index exposes
  dated catalogues and property-level results back through at least 2022, with
  guide prices and explicit sold, sold-prior and sold-after outcomes. Reconcile
  Coventry and any associated branch/trading-name identities before counting
  coverage, inventory every catalogue and lot, and deduplicate any
  shared-platform overlap. National completeness remains false.

## 27 October 2026 — Loveitts first-party event-archive expansion

- Inventoried **88 dated index entries** in the surviving first-party archive:
  **83 linked event pages** were captured and five dates had no retained
  property link. The linked events exposed **662 distinct property rows** from
  3 February 2022 through 13 October 2026, with all 662 property-detail pages
  snapshotted successfully and no detail-date mismatch or recovery failure.
- Excluded **80 exact date/address overlaps** already evidenced through the
  shared Auction House platform. The canonical shard therefore banks **582 net
  new individual appearances**: 582 address records, zero partial, zero
  undated, zero future-dated and zero duplicate appearance IDs. All 582 are
  exact-dated inside the current 20-year window and add Loveitts source-years
  **2022, 2023, 2024, 2025 and 2026**.
- Added **582 guide-price records**, **329 achieved sale prices** and **193
  published rent values**. The evidence-based sector split is 302 mixed-use,
  178 commercial, 76 residential, seven land and 19 unknown, giving a
  commercial/mixed-use increment of **480**. Outcomes remain distinct: 424
  sold, 64 sold-after, 88 sold-prior and six unsold.
- Reconciled the auctioneer family before counting coverage. **Loveitts
  Limited trading as Loveitts** is one operator; Auction House Coventry &
  Warwickshire remains shared-platform provenance and is not counted as an
  additional auctioneer. Every admitted row retains its original property URL
  and immutable event/detail source evidence.
- The rebuilt corpus contains **300,287 appearances**: **289,517 address
  records**, **10,770 partial records** and **292,705 exact-dated address
  appearances inside the current 20-year window**, including **99,468
  guide-price records** and **110,905 achieved-price records**. Source-register
  reconciliation and database publication completed successfully.
- **Next concrete growth target:** collect Butters John Bee's uncovered
  first-party catalogue/results archive at
  `https://buttersjohnbee.com/auction-catalogues`. Its current index publishes
  catalogue/result pairs across at least 2024–2026 while the source register
  has zero linked Butters John Bee appearances. Inventory the catalogues and
  their individual lots, preserve original result/catalogue URLs and immutable
  snapshots, reconcile branches as one operator/trading lineage, and exclude
  exact shared-platform overlap before claiming growth. National completeness
  remains false.

## 27 October 2026 — Butters John Bee paired catalogue/results expansion

- Reconciled **23 first-party catalogue/result pairs** from 22 January 2024
  through 14 September 2026. Every result sheet exposed a complete sequential
  lot table and together they contained **1,446 distinct source rows**.
- Banked **1,446 net-new individual appearances**: 1,446 address records, zero
  partial, zero undated, zero future-dated and zero duplicate-derived records.
  All 1,446 have exact dates inside the current 20-year window and newly cover
  Butters John Bee source-years **2024, 2025 and 2026**.
- Added **1,445 guide-price records**, **418 achieved sale prices** and **151
  rent values**. Sector evidence comprises 724 residential, 167 land, 37
  mixed-use, 36 commercial and 482 evidence-limited unknown appearances; the
  commercial/mixed-use increment is **73**. Published outcomes remain distinct:
  418 sold, 355 unsold, 97 sold-after, 237 sold-prior, 250 postponed and 89
  withdrawn.
- Catalogue pages enriched 1,419 result rows with property details, tenure or
  rent. The 27 printed postcode/address mismatches were left conservatively
  unenriched instead of being forced into possibly different legal interests.
  No exact global date/address overlap was excluded.
- Reconciled the operator before counting coverage. **Butters John Bee Limited
  (company 05289439)**, its lower-case trading style and its branches are one
  operator. Darlows, Haybrook and haart remain related group-brand context and
  are not counted as additional Butters John Bee auctioneers.
- Evidence is persisted as 23 event inventories, 23 immutable result-PDF byte
  snapshots, 23 catalogue text snapshots, the first-party archive snapshot and
  every original catalogue/result URL. The canonical shard contains 1,446
  unique appearance IDs and 1,446 unique source identities.
- The rebuilt corpus contains **301,739 appearances**: **290,969 address
  records**, **10,770 partial records**, **294,151 exact-dated appearances in
  the current 20-year window**, **100,913 guide-price records** and **111,323
  achieved-price records**. The separately completed bounded refresh added six
  future-dated address records before this focused run; these are not included
  in the 1,446 Butters growth claim. Undated remains 4,388 and future-dated is
  now 157. Collection, packaging, source-register reconciliation and protected
  publication completed successfully.
- A reusable next collector is prepared for **Purplebricks Online Auctions**.
  Its first-party GOTO `/search` route currently publishes a **2,778-card**
  denominator across 56 pages, but also mixes in undated Committed Offer cards.
  The tested parser now reconciles and excludes those non-auction cards instead
  of admitting them or failing the whole archive. Purplebricks identifies Genle
  Limited trading as GOTO Group (company 09790404) as its auction provider, so
  the branded channel and platform must not be counted as two auctioneers.
  Complete the 56-page inventory before claiming the net appearance count.
  National completeness remains false.

## 27 October 2026 — Purplebricks Online Auctions / GOTO complete archive

- Reconciled the complete retained first-party results grid: **2,778 published
  cards across 56 pages**. The collection banks **2,451 evidenced individual
  auction appearances** and retains **327 Committed Offer property cards** as
  explicit audit exclusions because the source does not evidence an auction
  appearance for them.
- The new canonical shard contains **2,451 unique appearance IDs** and **2,451
  unique source lot IDs**, with no duplicate source-evidence rows. It adds
  **2,450 address records** and one partial record. Of these, **2,406 are dated
  address appearances inside the current 20-year window**, seven are undated
  and 38 are future-dated; none of those categories is used to inflate another.
- Newly covered Purplebricks/GOTO source-years are **2020, 2021, 2022, 2023,
  2024, 2025 and 2026**. The evidence-based sector split is 1,647 residential,
  41 land, 19 mixed-use, 14 commercial and 730 unknown, giving a
  commercial/mixed-use increment of **33**.
- Added **79 achieved sale prices**, all attached to appearances inside the
  current 20-year window. The source supplies no admissible guide-price or rent
  increment. Published outcomes remain distinct: 2,121 sold-prior, 16
  sold-after, three sold, 110 unsold, 40 withdrawn and 161 unknown.
- Reconciled the operator before counting coverage. **Genle Limited (company
  09790404) trading as GOTO Group** operates the Purplebricks-branded auction
  channel, so the brand and platform are one operator/platform lineage rather
  than two auctioneers.
- Recovery fixes now preserve a stable-ID partial lot when the source omits its
  address, preserve a stable-ID address record when the source omits its date,
  and make date-range summaries null-safe. The focused parser, register and
  workflow suite passes 40 tests. Every admitted row retains its original URL
  and immutable page evidence, and the rebuilt database was verified before
  publication.
- The rebuilt corpus contains **304,199 appearances**: **293,428 address
  records**, **10,771 partial records**, **296,563 dated address appearances in
  the current 20-year window**, **100,918 guide-price records** and **111,404
  achieved-price records**. Undated appearances total 4,395 and future-dated
  appearances total 198.
- **Next concrete growth target:** collect Landmark Auctions Limited's
  first-party past-auctions inventory at
  `https://landmarkauctions.co.uk/past-auctions/`. On 27 October 2026 the live
  archive published 54 result cards while the corpus had no Landmark Auctions
  appearances. Inventory every lot and retain dates, prices, outcomes,
  original URLs and immutable snapshots; reconcile shared-platform or partner
  overlap before claiming growth. National completeness remains false.

## 27 October 2026 — Landmark Auctions retained-grid expansion

- Reconciled the complete surviving first-party EIG grid: **62 published
  auction-lot cards across two pages**, 62 distinct stable lot identities and
  all 62 detail pages. There are no malformed cards, non-auction exclusions,
  duplicate source rows or detail-recovery failures.
- Banked **62 net-new address appearances** and no partial or undated records.
  **55** are exact-dated inside the current 20-year window and seven are
  explicitly future-dated to 29 October 2026, so the future records are not
  counted as historical growth. Landmark source-years **2022 and 2026** are
  newly represented.
- Added **60 guide prices**, **seven achieved sale prices** and **15 published
  rent values**. Of the guides, 53 belong to appearances inside the current
  20-year window and seven belong to the future catalogue. The evidence-based
  sector split is 47 residential, eight land, four commercial and three
  mixed-use appearances; the commercial/mixed-use increment is **seven**.
- Preserved published outcomes individually: 19 sold-prior, one sold, 11
  unsold/no-bid, seven withdrawn, 17 postponed and seven current/future
  unknown listings. Achieved prices are populated only on the seven cards that
  publish one; other price fields remain null unless a first-party guide is
  present.
- Reconciled the operator before counting coverage. **Landmark Auctions
  Limited (company 13592079)** is one operator; Daniels Estate Agents and The
  Landmark Consultancy remain partner provenance and are not counted as
  additional auctioneers.
- The canonical shard contains 62 unique appearance IDs and 62 unique source
  lot IDs. Every row retains its original lot URL, one of two immutable grid
  snapshots and its immutable detail-page snapshot. The reusable EIG parser
  now supports both current `list-*` cards and the retained `grid-*` address,
  price and image markup; 53 focused local tests and 99 Actions tests pass.
- The rebuilt database contains **304,261 appearances**: **293,490 address
  records**, **10,771 partial records** and **296,618 appearances inside the
  current 20-year window**, including **100,971 guide-price records** and
  **111,411 achieved-price records** in that window. Undated appearances remain
  4,395 and future-dated appearances are now 205. Packaging, source-register
  reconciliation and protected publication completed successfully.
- **Next concrete growth target:** inventory Aston Vaughan Auctions' first
  completed first-party sale, whose published result article reports 18
  properties offered and 16 sold, then reconcile its individual catalogue and
  listing evidence against that denominator. Keep its announced 26 November
  2026 catalogue explicitly future-dated, reconcile agency/auction trading
  identities before counting operator coverage, and bank only evidenced
  individual property appearances. National completeness remains false.

## 27 October 2026 — Auction House Online shared-platform event expansion

- Aston Vaughan's first completed sale was bounded without inventing records.
  Its first-party article verifies only **18 offered / 16 sold**; the official
  auction site blocks retrieval and the only exposed historical lot table is
  subscription-only. No individual row was admitted from inconsistent search
  snippets. Revisit this route only when accessible first-party lot evidence
  or an immutable equivalent becomes available.
- Switched to the accessible first-party Auction House Online event
  `https://online.auctionhouse.co.uk/past-auctions/75792` and reconciled its
  complete **92-card** published denominator, 92 distinct stable identities
  and all 92 detail pages. No malformed card, non-auction exclusion or detail
  recovery failure remains.
- Excluded **53 exact date/address overlaps** already banked through regional
  Auction House shards. Those URLs and overlap decisions remain in the source
  audit and are not claimed as growth. The canonical shard banks **39 net-new
  address appearances**, all exact-dated inside the current 20-year window;
  there are zero partial, undated or future-dated additions. Auction House
  Online source-year **2025** is newly represented.
- Added **39 guide-price records**, **one achieved-price record** and no rent
  values. The evidence-based sector split is 30 residential, one land, one
  mixed-use and seven unknown appearances, giving a commercial/mixed-use
  increment of **one**. Outcomes remain distinct: 27 unsold/no-bid, five
  withdrawn, four sold-prior and three postponed.
- Preserved the responsible branch/channel label from each property detail
  page while treating **AUCTION HOUSE UK LIMITED (company 06025583)** as the
  one shared-platform operator. Regional labels and the Online channel are
  provenance, not additional legal operators.
- The rebuilt corpus contains **304,300 appearances**: **293,529 address
  records**, **10,771 partial records** and **296,657 dated appearances inside
  the current 20-year window**, including **101,010 guide-price records** and
  **111,412 achieved-price records**. Undated remains 4,395 and future-dated
  remains 205. The focused 58-test suite, complete database rebuild, source
  register reconciliation and protected publication passed.
- **Next concrete growth target:** collect the adjacent first-party Auction
  House Online event `https://online.auctionhouse.co.uk/past-auctions/74284`,
  which publishes **44 individual result cards** dated in October 2025. Reuse
  the branch-attributing collector, require every detail page and exclude exact
  regional-shard overlaps before claiming net growth. National completeness
  remains false.

## 27 October 2026 — Auction House Online October event expansion

- Reconciled the complete first-party Auction House Online event
  `https://online.auctionhouse.co.uk/past-auctions/74284`: **44 published
  cards**, 44 distinct stable source identities and all 44 detail pages. There
  are no malformed cards, non-auction exclusions, duplicate source identities
  or detail-recovery failures.
- Excluded **31 exact date/address overlaps** already present through regional
  Auction House evidence. The canonical shard banks **13 net-new address
  appearances**, all exact-dated inside the current 20-year window. There are
  zero partial, undated or future-dated additions and no duplicate-derived
  growth claim.
- Added **13 guide-price records**, **one achieved-price record** and no rent
  values. The evidence-based sector split is eight residential, one land, one
  commercial and three unknown appearances; the commercial/mixed-use
  increment is **one commercial and zero mixed-use**. Published outcomes remain
  distinct: five unsold, four sold-prior, three postponed and one sold.
- Preserved the responsible branch/channel label from every admitted detail
  page. Thirteen net-new appearances span nine regional Auction House labels,
  while **AUCTION HOUSE UK LIMITED (company 06025583)** remains the single
  shared-platform operator; branches and the Online channel are provenance,
  not new legal operators.
- The rebuilt corpus contains **304,313 appearances**: **293,542 address
  records**, **10,771 partial records** and **296,670 dated appearances inside
  the current 20-year window**, including **101,023 guide-price records** and
  **111,413 achieved-price records**. Undated remains 4,395 and future-dated
  remains 205. Collection, strict overlap audit, database rebuild and protected
  publication completed successfully.
- **Next concrete growth target:** collect the larger adjacent first-party
  Auction House Online event
  `https://online.auctionhouse.co.uk/past-auctions/67455`, which publishes **55
  individual result cards**, principally dated 24–25 March 2025. Reuse the
  branch-attributing collector, require all 55 detail pages and exclude only
  exact regional-shard date/address overlaps before claiming net growth.
  National completeness remains false.

## 27 October 2026 — Auction House Online March event expansion

- Reconciled the complete first-party Auction House Online event
  `https://online.auctionhouse.co.uk/past-auctions/67455`: **55 published
  cards**, 55 distinct stable source identities and all 55 detail pages. There
  are no malformed cards, non-auction exclusions, duplicate source identities
  or detail-recovery failures.
- Excluded **24 exact date/address overlaps** already present through regional
  Auction House evidence. The canonical shard banks **31 net-new address
  appearances**, all exact-dated inside the current 20-year window. There are
  zero partial, undated or future-dated additions and no duplicate-derived
  growth claim.
- Added **31 guide-price records**, **one achieved-price record** and **one
  published rent value**. The evidence-based sector split is 11 residential,
  eight land, one commercial, one mixed-use and ten unknown appearances; the
  commercial/mixed-use increment is **two**. Published outcomes remain
  distinct: 20 unsold, six withdrawn, two postponed, and one each sold,
  sold-prior and sold-after.
- Preserved 11 responsible regional branch/channel labels from the detail
  pages while treating **AUCTION HOUSE UK LIMITED (company 06025583)** as the
  single shared-platform operator. Branches and the Online channel remain
  provenance, not additional legal operators.
- The rebuilt corpus contains **304,344 appearances**: **293,573 address
  records**, **10,771 partial records** and **296,701 dated appearances inside
  the current 20-year window**, including **101,054 guide-price records** and
  **111,414 achieved-price records**. Undated remains 4,395 and future-dated
  remains 205. Collection, strict overlap audit, database rebuild and protected
  publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/67663`, which publishes
  **47 individual result cards**, principally dated in April 2025. Reuse the
  branch-attributing collector, require all 47 detail pages and exclude only
  exact regional-shard date/address overlaps before claiming net growth.
  National completeness remains false.

## 27 October 2026 — Auction House Online April event expansion

- Reconciled the complete first-party Auction House Online event
  `https://online.auctionhouse.co.uk/past-auctions/67663`: **47 published
  cards**, 47 distinct stable source identities and all 47 detail pages. There
  are no malformed cards, non-auction exclusions, duplicate source identities
  or detail-recovery failures.
- Excluded **24 exact date/address overlaps** already present through regional
  Auction House evidence. The canonical shard banks **23 net-new address
  appearances**, all exact-dated inside the current 20-year window. There are
  zero partial, undated or future-dated additions and no duplicate-derived
  growth claim. Auction House Online source-year **2025** remains evidenced by
  a newly covered event.
- Added **23 guide-price records**, **four achieved-price records** and no rent
  values. The evidence-based sector split is 12 residential, one land and ten
  unknown appearances; the commercial/mixed-use increment is **zero**.
  Published outcomes remain distinct: 15 unsold, four sold-prior, two sold and
  two withdrawn.
- Preserved 13 responsible regional branch/channel labels from the detail
  pages while treating **AUCTION HOUSE UK LIMITED (company 06025583)** as the
  single shared-platform operator. Branches and the Online channel remain
  provenance, not additional legal operators.
- A separately pre-existing bounded refresh completed before this focused
  event and banked **125 net additional address appearances**. That independent
  delta is not included in the April event's 23-record claim; it contributed
  121 dated appearances inside the current 20-year window, four future-dated
  appearances, 113 guide-price records and 27 achieved-price records, with a
  one-record correction in the rebuilt corpus.
- After both sequential, non-overlapping passes, the rebuilt corpus contains
  **304,492 appearances**: **293,721 address records**, **10,771 partial
  records** and **296,845 dated appearances inside the current 20-year
  window**, including **101,190 guide-price records** and **111,445
  achieved-price records** in that window. Undated remains 4,395 and
  future-dated is 209. Collection, strict overlap audit, database rebuild and
  protected publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/69595`, which publishes
  **59 individual result cards** dated 27 May 2025. Reuse the
  branch-attributing collector, require all 59 detail pages and exclude only
  exact regional-shard date/address overlaps before claiming net growth.
  National completeness remains false.

## 27 October 2026 — Auction House Online 11 November event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/75000` to **72 published
  cards**, 72 distinct stable source identities and all 72 detail pages. The
  first-party page is unpaginated; no malformed, non-auction or duplicate
  source identities were admitted.
- Excluded **44 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **28 net-new
  address appearances**, all dated within the current 20-year window. Partial,
  undated and future-dated additions are all zero.
- Added **28 guide-price records**, no achieved-price records and **one
  published rent value**. The evidence-based sector split is 21 residential,
  five unknown, one commercial and one land appearance; commercial/mixed-use
  growth is **one**. Outcomes remain distinct: 20 unsold, five postponed and
  three withdrawn.
- Preserved ten responsible regional branch labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,561 appearances**: **293,790 address
  records**, **10,771 partial records** and **296,914 dated appearances inside
  the current 20-year window**, including **101,259 guide-price records** and
  **111,446 achieved-price records**. Undated remains 4,395 and future-dated
  remains 209. Collection, overlap audit, rebuild and protected checkpoint
  publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/71414`, dated 29 July
  2025 and exposing 70 individual result cards. Require the live denominator,
  every detail page and strict exact-overlap exclusion before claiming growth.
  National completeness remains false.

## 27 October 2026 — Auction House Online 29 July event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/71414` to **70 published
  cards**, 70 distinct stable source identities and all 70 detail pages. The
  first-party grid is unpaginated; no malformed, non-auction or duplicate
  source identities were admitted.
- Excluded **42 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **28 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate identities added
  are zero. This adds one reconciled Auction House Online event/source-year
  pair for 2025 without claiming a new legal operator-year.
- Added **28 guide-price records**, no achieved-price records and no rent
  values. The evidence-based sector split is 16 residential, ten unknown, one
  commercial and one land appearance; commercial/mixed-use growth is **one**.
  Outcomes remain distinct: 22 unsold, three sold-prior and three postponed.
- Preserved ten responsible regional branch labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,589 appearances**: **293,818 address
  records**, **10,771 partial records** and **296,942 dated appearances inside
  the current 20-year window**, including **101,287 guide-price records** and
  **111,446 achieved-price records**. Undated remains 4,395 and future-dated
  remains 209. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/69260`, dated 20 May
  2025 and exposing 43 individual result cards. Require the live denominator,
  every detail page and strict exact-overlap exclusion before claiming growth.
  Event 69595 remains terminal until a materially new retrieval route exists.
  National completeness remains false.

## 27 October 2026 — Auction House Online 20 May event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/69260` to **43 published
  cards**, 43 distinct stable source identities and all 43 detail pages. The
  first-party grid is unpaginated; no malformed, non-auction or duplicate
  source identities were admitted.
- Excluded **25 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **18 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate identities added
  are zero. This adds one reconciled Auction House Online event/source-year
  pair for 2025 without claiming a new legal operator-year.
- Added **18 guide-price records**, no achieved-price records and no rent
  values. The evidence-based sector split is 13 residential, three unknown and
  two land appearances; commercial/mixed-use growth is **zero**. Outcomes
  remain distinct: 15 unsold, two withdrawn and one sold-prior.
- Preserved ten responsible regional branch labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,607 appearances**: **293,836 address
  records**, **10,771 partial records** and **296,960 dated appearances inside
  the current 20-year window**, including **101,305 guide-price records** and
  **111,446 achieved-price records**. Undated remains 4,395 and future-dated
  remains 209. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/70967`, dated 24 June
  2025 and exposing 54 individual result cards. Require the live denominator,
  every detail page and strict exact-overlap exclusion before claiming growth.
  Event 69595 remains terminal until a materially new retrieval route exists.
  National completeness remains false.

## 28 October 2026 — Auction House Online 24 June event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/70967` to **54 published
  cards**, 54 distinct stable source identities and all 54 detail pages. The
  grid is unpaginated; no malformed, non-auction or duplicate source
  identities were admitted.
- Excluded **27 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **27 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate identities added
  are zero. This adds one reconciled Auction House Online event/source-year
  pair for 2025 without claiming a new legal operator-year.
- Added **27 guide-price records**, **one achieved-price record** and no rent
  values. The evidence-based sector split is 16 residential, nine unknown, one
  commercial and one land appearance; commercial/mixed-use growth is **one
  commercial and zero mixed-use**. Outcomes remain distinct: 15 unsold, five
  sold-prior, four postponed, two withdrawn and one sold.
- Preserved 14 responsible regional branch labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,634 appearances**: **293,863 address
  records**, **10,771 partial records** and **297,016 dated appearances inside
  the current 20-year window**, including **101,343 guide-price records** and
  **111,447 achieved-price records**. Undated remains 4,395. Future-dated
  records are 180 after the reporting window advanced to 28 October; no
  future records were discarded. Collection, immutable snapshot banking,
  overlap audit, database rebuild and protected checkpoint publication
  completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/72575`, dated 30
  September 2025 and exposing **100 individual result cards**. Require the
  live denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Event 69595 remains terminal until a materially new
  retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 30 September event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/72575` to **100 published
  cards**, 100 distinct stable source identities and all 100 detail pages. The
  grid is unpaginated; no malformed, non-auction or duplicate source
  identities were admitted.
- Excluded **63 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **37 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate identities added
  are zero. This adds one reconciled Auction House Online event/source-year
  pair for 2025 without claiming a new legal operator-year.
- Added **37 guide-price records**, **one achieved-price record** and no rent
  values. The evidence-based sector split is 23 unknown, 11 residential and
  three commercial appearances; commercial/mixed-use growth is **three
  commercial and zero mixed-use**. Outcomes remain distinct: 30 unsold, three
  sold-prior, two withdrawn, one postponed and one sold.
- Preserved 12 responsible regional branch labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,672 appearances**: **293,901 address
  records**, **10,771 partial records** and **297,054 dated appearances inside
  the current 20-year window**, including **101,380 guide-price records** and
  **111,448 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/75333`, dated 12-13
  January 2026 and exposing **104 individual result cards**. Require the live
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Event 69595 remains terminal until a materially new
  retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 13 January event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/75333` to **104 published
  cards**, 104 distinct stable source identities and all 104 detail pages. The
  first detail pass rejected the batch when transient page failures prevented
  complete branch attribution; a bounded grid-first recovery then completed
  every detail page and admitted no partial enrichment.
- Excluded **50 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **54 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate identities added
  are zero. Individual dates span 19 December 2025 to 13 January 2026, adding
  two reconciled event-shard source-year pairs without claiming a new legal
  operator-year.
- Added **54 guide-price records**, **four achieved-price records** and no rent
  values. The evidence-based sector split is 38 residential, ten unknown,
  three land, two commercial and one mixed-use appearance; commercial/mixed-use
  growth is **two commercial and one mixed-use**. Outcomes remain distinct: 39
  unsold, five postponed, four withdrawn, four sold and two sold-prior.
- Preserved 17 published regional/channel labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,726 appearances**: **293,955 address
  records**, **10,771 partial records** and **297,108 dated appearances inside
  the current 20-year window**, including **101,434 guide-price records** and
  **111,452 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit,
  database rebuild and protected checkpoint publication completed
  successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82458`, dated 29-30
  June 2026 and exposing **102 individual result cards**. Require the live
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Event 69595 remains terminal until a materially new
  retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 30 June event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82458` to **102 published
  cards**, 102 distinct stable source identities and all 102 detail pages. The
  unpaginated grid and bounded detail recovery completed without failures or
  partial enrichment.
- Excluded **42 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **60 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are all zero; duplicate source identities
  added are zero. Individual dates span 9 to 30 June 2026, adding one
  reconciled event-shard source-year without claiming a new legal
  operator-year.
- Added **60 guide-price records**, no achieved-price records and no rent
  values. The evidence-based sector split is 36 residential, 21 unknown, two
  land and one commercial appearance; commercial/mixed-use growth is **one
  commercial and zero mixed-use**. Outcomes remain distinct: 46 unsold, seven
  withdrawn, five sold-prior and two postponed.
- Preserved 15 published regional/channel labels while treating **AUCTION
  HOUSE UK LIMITED (company 06025583)** as the single shared-platform
  operator. Branches and the Online channel remain provenance, not additional
  legal operators.
- The rebuilt corpus contains **304,786 appearances**: **294,015 address
  records**, **10,771 partial records** and **297,168 dated appearances inside
  the current 20-year window**, including **101,494 guide-price records** and
  **111,452 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit and
  database rebuild and protected checkpoint publication completed
  successfully.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/79607`, dated 30-31
  March 2026 and exposing **101 individual result cards**. Require the live
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Event 69595 remains terminal until a materially new
  retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 31 March event blocked before capture

- Targeted first-party event
  `https://online.auctionhouse.co.uk/past-auctions/79607`, whose independently
  observed catalogue exposes **101 individual result cards**. The collection
  runner exhausted five requests against the event route; the final request
  ended in a 120-second read timeout before the archive index arrived.
- No card, detail page or immutable event snapshot was admitted. Net-new
  appearances, address records, dated address records inside the 20-year
  window, commercial/mixed-use records, source-years, guides, achieved prices
  and rents are therefore all **zero**. Partial, undated, future-dated and
  duplicate additions are also zero; this is a blocker, not collection growth.
- The protected banking stage, database rebuild and checkpoint publication
  still completed. The corpus remains at **304,786 appearances**, **294,015
  address records**, **10,771 partial records** and **297,168 dated appearances
  inside the current 20-year window**, including **101,494 guide-price records**
  and **111,452 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. No captured evidence was discarded.
- **Next concrete growth target:** move to the separate first-party Auction
  House Online event `https://online.auctionhouse.co.uk/past-auctions/79785`,
  dated 13-14 April 2026 and exposing **99 actual visible cards**. Lot-number
  gaps are not extra properties. Require the live-card denominator, every
  detail page and strict exact-overlap exclusion before claiming growth. Do not
  retry events 69595 or 79607 until the upstream response changes or a
  materially new retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 14 April event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/79785?lotResultType=All`
  to **99 published cards**, 99 stable source identities and all 99 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **50 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **49 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 20 March to 14 April 2026, adding one reconciled
  event-shard source-year without claiming a new legal operator-year.
- Added **49 guide-price records**, **one achieved-price record** and **three
  rent values**. The evidence-based sector split is 32 residential, 12 unknown,
  three land, one commercial and one mixed-use appearance. Outcomes remain
  distinct: 38 unsold, four postponed, four withdrawn, two sold-prior and one
  sold.
- Preserved 17 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator. Branches
  remain provenance, not additional legal operators.
- The rebuilt corpus contains **304,835 appearances**: **294,064 address
  records**, **10,771 partial records** and **297,217 dated appearances inside
  the current 20-year window**, including **101,543 guide-price records** and
  **111,453 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully.
- The first trigger attempt exposed and repaired a truncated continuation
  checkpoint before any event rows were admitted. Its complete 1,797,499-byte
  content-addressed blob was restored and the exact pre-collection suite passed
  114 tests. The April trigger is now event-specific; the already-complete
  November event cannot be refreshed by this route again.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/78487`, dated 23-24
  February 2026 and exposing **92 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 24 February event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/78487?lotResultType=All`
  to **92 published cards**, 92 stable source identities and all 92 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **40 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **52 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 9 to 24 February 2026, adding one reconciled
  event-shard source-year without claiming a new legal operator-year.
- Added **48 guide-price records**, **one achieved-price record** and **one rent
  value**. The evidence-based sector split is 31 residential, 14 unknown,
  three commercial, three land and one mixed-use appearance.
  Commercial/mixed-use growth is **three commercial and one mixed-use**.
  Outcomes remain distinct: 40 unsold, four sold-prior, four withdrawn, three
  postponed and one sold.
- Preserved 15 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator. Branches
  remain provenance, not additional legal operators.
- The rebuilt corpus contains **304,887 appearances**: **294,116 address
  records**, **10,771 partial records** and **297,269 dated appearances inside
  the current 20-year window**, including **101,591 guide-price records** and
  **111,454 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully. The
  two workflow test stages passed 388 and 115 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/79291`, dated 16-17
  March 2026 and exposing **81 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 17 March event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/79291?lotResultType=All`
  to **81 published cards**, 81 stable source identities and all 81 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **32 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **49 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 27 February to 17 March 2026, adding one
  reconciled event-shard source-year without claiming a new legal
  operator-year.
- Added **49 guide-price records**, **three achieved-price records** and **one
  rent value**. The evidence-based sector split is 32 residential, 14 unknown,
  two commercial and one land appearance. Commercial/mixed-use growth is **two
  commercial and zero mixed-use**. Outcomes remain distinct: 33 unsold, eight
  withdrawn, four sold-prior, three sold and one postponed.
- Preserved 15 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator. Branches
  remain provenance, not additional legal operators.
- The rebuilt corpus contains **304,936 appearances**: **294,165 address
  records**, **10,771 partial records** and **297,318 dated appearances inside
  the current 20-year window**, including **101,640 guide-price records** and
  **111,457 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully. The
  two workflow test stages passed 388 and 116 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/79158`, dated 23-24
  March 2026 and exposing **73 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 24 March event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/79158?lotResultType=All`
  to **73 published cards**, 73 stable source identities and all 73 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **35 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **38 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 24 February to 24 March 2026, adding one
  reconciled event-shard source-year without claiming a new legal
  operator-year.
- Added **38 guide-price records**, **one achieved-price record** and no rent
  values. The evidence-based sector split is 23 residential, 14 unknown and
  one commercial appearance; commercial/mixed-use growth is **one commercial
  and zero mixed-use**. Outcomes remain distinct: 26 unsold, six withdrawn,
  three sold-prior, two postponed and one sold.
- Preserved 12 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator.
  Branches remain provenance, not additional legal operators.
- The rebuilt corpus contains **304,991 appearances**: **294,220 address
  records**, **10,771 partial records** and **297,373 dated appearances inside
  the current 20-year window**, including **101,695 guide-price records** and
  **111,459 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully. The
  two historical workflow test stages passed 388 and 117 tests; the protected
  live-board publication revalidation passed 1,357 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/80208`, dated 20-21
  April 2026 and exposing **72 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 21 April event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/80208?lotResultType=All`
  to **72 published cards**, 72 stable source identities and all 72 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **40 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **32 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 8 to 21 April 2026, adding one reconciled
  event-shard source-year without claiming a new legal operator-year.
- Added **32 guide-price records**, **one achieved-price record** and **two rent
  values**. The evidence-based sector split is 13 residential, 13 unknown,
  five land and one commercial appearance; commercial/mixed-use growth is
  **one commercial and zero mixed-use**. Outcomes remain distinct: 26 unsold,
  two withdrawn, two sold-prior and two postponed.
- Preserved 11 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator.
  Branches remain provenance, not additional legal operators.
- The rebuilt corpus contains **305,023 appearances**: **294,252 address
  records**, **10,771 partial records** and **297,405 dated appearances inside
  the current 20-year window**, including **101,727 guide-price records** and
  **111,460 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully. The
  two historical workflow test stages passed 388 and 118 tests; the protected
  live-board publication revalidation passed 1,358 tests and 22 subtests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/80207`, dated 27-28
  April 2026 and exposing **78 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 28 April event expansion

- Reconciled first-party event
  `https://online.auctionhouse.co.uk/past-auctions/80207?lotResultType=All`
  to **78 published cards**, 78 stable source identities and all 78 detail
  pages. The explicit all-results route is unpaginated and completed without
  detail-recovery failures or partial enrichment.
- Excluded **29 exact date/address overlaps** already evidenced through
  regional Auction House shards. The canonical event shard banks **49 net-new
  address appearances**, all dated inside the current 20-year window. Partial,
  undated and future-dated additions are zero; duplicate source identities are
  zero. Individual dates span 2 to 28 April 2026, adding one reconciled
  event-shard source-year without claiming a new legal operator-year.
- Added **49 guide-price records**, no achieved-price records and **four rent
  values**. The evidence-based sector split is 28 residential, 17 unknown, two
  land and two commercial appearances; commercial/mixed-use growth is **two
  commercial and zero mixed-use**. Outcomes remain distinct: 38 unsold, five
  withdrawn, four postponed and two sold-prior.
- Preserved 16 published regional labels while treating **AUCTION HOUSE UK
  LIMITED (company 06025583)** as the single shared-platform operator.
  Branches remain provenance, not additional legal operators.
- The rebuilt corpus contains **305,072 appearances**: **294,301 address
  records**, **10,771 partial records** and **297,454 dated appearances inside
  the current 20-year window**, including **101,776 guide-price records** and
  **111,460 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Collection, immutable snapshot banking, overlap audit, database
  rebuild and protected checkpoint publication completed successfully. The
  two historical workflow test stages passed 388 and 119 tests; the protected
  live-board publication revalidation passed 1,359 tests and 22 subtests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82154`, dated 8-9
  June 2026 and exposing **88 actual visible cards**. Require the live-card
  denominator, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595 or 79607 until their upstream
  responses change or a materially new retrieval route exists. National
  completeness remains false.

## 28 October 2026 — Auction House Online 9 June event blocked before capture

- Targeted first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82154?lotResultType=All`,
  whose independently reconciled archive index reports **88 individual result
  cards**. The bounded request exhausted the explicit all-results route and
  ended in a 120-second read timeout before the archive index arrived.
- No card, detail page or immutable event snapshot was admitted. Net-new
  appearances, address records, dated address records inside the 20-year
  window, commercial/mixed-use records, source-years, guides, achieved prices
  and rents are therefore all **zero**. Partial, undated, future-dated and
  duplicate additions are also zero; this is an upstream blocker, not
  collection growth.
- The two historical test stages passed **388 and 120 tests**. Protected
  source-corpus banking, the database rebuild and checkpoint publication also
  completed successfully, preserving all prior evidence. The corpus remains
  at **305,072 appearances**, **294,301 address records**, **10,771 partial
  records** and **297,454 dated appearances inside the current 20-year
  window**, including **101,776 guide-price records** and **111,460
  achieved-price records**. Undated remains 4,395 and future-dated remains 180.
- **Next concrete growth target:** move to the separate first-party Auction
  House Online event `https://online.auctionhouse.co.uk/past-auctions/81218`,
  dated 25-26 May 2026 and exposing **80 actual result cards**. Require the
  live-card denominator, every detail page and strict exact-overlap exclusion
  before claiming growth. Do not retry events 69595, 79607 or 82154 until the
  upstream response changes or a materially different retrieval route exists.
  National completeness remains false.

## 28 October 2026 — Auction House Online 26 May event fully reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/81218?lotResultType=All`.
  Its **80 visible result cards**, 80 stable source identities and 80 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **49 net-new appearances and address records**, all dated inside the
  current 20-year window. Thirty-one exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **49 guide-price records**, **one achieved-price record** and **one rent
  value**. The new sector split is 28 unknown, 20 residential and one
  commercial appearance; commercial/mixed-use growth is **one commercial and
  zero mixed-use**. Published outcomes remain distinct: 37 unsold, seven
  postponed, three withdrawn and two sold-prior.
- Preserved individual dates from 13 to 26 May 2026. Thirteen published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,121 appearances**, **294,350 address
  records**, **10,771 partial records** and **297,503 dated appearances inside
  the current 20-year window**, including **101,825 guide-price records** and
  **111,461 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Both workflow test stages passed 388 and 121 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/81603`, dated 1-2 June
  2026 and exposing **62 actual result cards**. Require all detail pages and
  strict exact-overlap exclusion before claiming growth. Do not retry events
  69595, 79607 or 82154 until their upstream response changes or a materially
  different retrieval route exists. National completeness remains false.

## 28 October 2026 — Auction House Online 2 June event fully reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/81603?lotResultType=All`.
  Its **62 visible result cards**, 62 stable source identities and 62 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **36 net-new appearances and address records**, all dated inside the
  current 20-year window. Twenty-six exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **36 guide-price records**, no achieved-price records and **two rent
  values**. The evidence-based sector split is 20 residential, 13 unknown, two
  mixed-use and one land appearance; commercial/mixed-use growth is **zero
  commercial and two mixed-use**. Outcomes remain distinct: 29 unsold, three
  postponed, three withdrawn and one sold-prior.
- Preserved individual dates from 29 April to 2 June 2026. Eleven published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,157 appearances**, **294,386 address
  records**, **10,771 partial records** and **297,539 dated appearances inside
  the current 20-year window**, including **101,861 guide-price records** and
  **111,461 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Both workflow test stages passed 388 and 122 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/81697`, dated 15-16
  June 2026 and exposing **73 actual result cards**. Require all detail pages
  and strict exact-overlap exclusion before claiming growth. Do not retry
  events 69595, 79607 or 82154 until their upstream response changes or a
  materially different retrieval route exists. National completeness remains
  false.

## 28 October 2026 — Auction House Online 16 June event fully reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/81697?lotResultType=All`.
  Its **73 visible result cards**, 73 stable source identities and 73 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **43 net-new appearances and address records**, all dated inside the
  current 20-year window. Thirty exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **43 guide-price records**, **one achieved-price record** and **two rent
  values**. The evidence-based sector split is 23 residential, 19 unknown and
  one land appearance; commercial/mixed-use growth is **zero commercial and
  zero mixed-use**. Outcomes remain distinct: 33 unsold, four withdrawn, four
  postponed, one sold and one sold-prior.
- Preserved individual dates from 2 to 16 June 2026. Fifteen published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,200 appearances**, **294,429 address
  records**, **10,771 partial records** and **297,582 dated appearances inside
  the current 20-year window**, including **101,904 guide-price records** and
  **111,462 achieved-price records**. Undated remains 4,395 and future-dated
  remains 180. Both workflow test stages passed 388 and 123 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82282`, dated 22-23
  June 2026 and exposing **77 actual result cards**. Require all detail pages
  and strict exact-overlap exclusion before claiming growth. Do not retry
  events 69595, 79607 or 82154 until their upstream response changes or a
  materially different retrieval route exists. National completeness remains
  false.

## 28 October 2026 — Auction House Online 23 June event fully reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82282?lotResultType=All`.
  Its **77 visible result cards**, 77 stable source identities and 77 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **52 net-new appearances and address records**, all dated inside the
  current 20-year window. Twenty-five exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **52 guide-price records**, **two achieved-price records** and **two rent
  values**. The evidence-based sector split is 28 residential, 22 unknown and
  two land appearances; commercial/mixed-use growth is **zero commercial and
  zero mixed-use**. Outcomes remain distinct: 41 unsold, five sold-prior, four
  postponed and two withdrawn.
- Preserved individual dates from 20 May to 23 June 2026. Thirteen published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,386 appearances**, **294,615 address
  records**, **10,771 partial records** and **297,761 dated appearances inside
  the current 20-year window**, including **101,953 guide-price records** and
  **111,479 achieved-price records**. Undated remains 4,395 and future-dated
  remains 187. Both workflow test stages passed 389 and 124 tests.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82831`, dated 6-7 July
  2026. Its result page exposes **64 actual property cards**, while the archive
  index headline says 62; reconcile that two-card discrepancy and every detail
  page before claiming growth. Do not retry events 69595, 79607 or 82154 until
  their upstream response changes or a materially different retrieval route
  exists. National completeness remains false.

## 28 October 2026 — Auction House Online 7 July event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82831?lotResultType=All`.
  The current response and archive index both expose **62 result cards**; all
  62 stable source identities and 62 detail pages reconcile, with immutable
  index and lot snapshots banked. Two cards visible during target discovery
  had disappeared before collection and were not manufactured or counted.
- Admitted **9 net-new appearances and address records**, all dated inside the
  current 20-year window. Fifty-three exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **9 guide-price records**, **zero achieved-price records** and **zero
  rent values**. The evidence-based sector split is seven residential, one
  land and one unknown appearance; commercial/mixed-use growth is **zero
  commercial and zero mixed-use**. Outcomes remain distinct: three sold-prior,
  four withdrawn, one unsold and one postponed.
- Preserved individual dates from 26 June to 7 July 2026. Seven published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,395 appearances**, **294,624 address
  records**, **10,771 partial records** and **297,770 dated appearances inside
  the current 20-year window**, including **101,962 guide-price records** and
  **111,479 achieved-price records**. Undated remains 4,395 and future-dated
  remains 187. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82742`, dated 13-14
  July 2026. Its result page and archive index expose **52 actual property
  cards**; require all detail pages and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595, 79607 or 82154 until their
  upstream response changes or a materially different retrieval route exists.

## 28 October 2026 — Auction House Online 14 July event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82742?lotResultType=All`.
  Its **52 visible result cards**, 52 stable source identities and 52 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **5 net-new appearances and address records**, all dated inside the
  current 20-year window. Forty-seven exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **5 guide-price records**, **one achieved-price record** and **zero rent
  values**. The evidence-based sector split is one residential and four
  unknown appearances; commercial/mixed-use growth is **zero commercial and
  zero mixed-use**. Outcomes remain distinct: two sold-prior, two postponed
  and one withdrawn.
- Preserved individual dates from 2 to 13 July 2026. Four published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,400 appearances**, **294,629 address
  records**, **10,771 partial records** and **297,775 dated appearances inside
  the current 20-year window**, including **101,967 guide-price records** and
  **111,480 achieved-price records**. Undated remains 4,395 and future-dated
  remains 187. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/83233`, dated 21 July
  2026. Its archive index exposes **64 individual cards**; require the
  all-results grid, every detail page and strict exact-overlap exclusion before
  claiming growth. Do not retry events 69595, 79607 or 82154 until their
  upstream response changes or a materially different retrieval route exists.
  National completeness remains false.

## 28 October 2026 — Auction House Online 21 July event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/83233?lotResultType=All`.
  Its **64 visible result cards**, 64 stable source identities and 64 detail
  pages reconcile exactly; immutable index and lot snapshots were banked.
- Admitted **6 net-new appearances and address records**, all dated inside the
  current 20-year window. Fifty-eight exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **6 guide-price records**, **zero achieved-price records** and **one rent
  value**. The evidence-based sector split is three residential, one land and
  two unknown appearances; commercial/mixed-use growth is **zero commercial
  and zero mixed-use**. Outcomes remain distinct: three sold-prior, two
  withdrawn and one postponed.
- Preserved individual dates from 2 to 20 July 2026. Four published
  regional/channel labels remain provenance under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,406 appearances**, **294,635 address
  records**, **10,771 partial records** and **297,781 dated appearances inside
  the current 20-year window**, including **101,973 guide-price records** and
  **111,480 achieved-price records**. Undated remains 4,395 and future-dated
  remains 187. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/82834`, dated 28 July
  2026. Its all-results grid exposes **88 individual cards**; require every
  detail page and strict exact-overlap exclusion before claiming growth. Do
  not retry events 69595, 79607 or 82154 until their upstream response changes
  or a materially different retrieval route exists. National completeness
  remains false.



## 28 October 2026 — protected rotation checkpoint and focused 28 July target

The completed protected rotation banked 41 unique address appearances without removals or duplicate appearance IDs. Forty Town & Country Property Auctions records retain the exact 28 October 2026 date: 15 residential, two commercial, three land and 20 sector-unknown. Their published outcomes remain distinct (22 no bids, nine unsold, seven sold and two postponed), with seven achieved prices. One Auction House South West sold-prior record dated 17 November 2026 is future-dated and carries one published guide. One existing Town & Country record also gained achieved-price evidence. No new source-year or legal operator-year is claimed.

The rebuilt corpus checkpoint is 305,487 appearances, including 294,716 address records and 297,860 appearances in the preceding twenty-year window. The next concrete growth target remains Auction House Online event 82834 at https://online.auctionhouse.co.uk/past-auctions/82834. Its first-party all-results grid exposes 88 individual cards for 28 July 2026. Reconcile every stable source identity and detail page, preserve dates, guides, achieved prices, rents, outcomes, original URLs and immutable snapshots, and exclude only exact overlaps. Auction House regional labels remain branch/channel attribution under AUCTION HOUSE UK LIMITED. If this event is unavailable, move to event 83949 (46 first-party cards dated 4 August 2026) rather than revisiting terminal blockers. National completeness remains false.


## 28 October 2026 — Auction House Online 28 July event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/82834?lotResultType=All`.
  The collector now requires the independently observed **88-card** denominator;
  88 visible cards, 88 stable source identities, the published count of 88 and
  all 88 detail pages reconcile exactly. Immutable index and lot snapshots were
  banked.
- Admitted **12 net-new appearances and address records**, all dated inside the
  current 20-year window. Seventy-six exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **12 guide-price records**, **one achieved-price record** and **zero rent
  values**. The evidence-based sector split is five residential, one land, one
  commercial and five unknown appearances; commercial/mixed-use growth is
  **one commercial and zero mixed-use**. Outcomes remain distinct: four
  withdrawn, two postponed, one unsold, four sold-prior and one sold.
- Preserved individual dates from 14 to 28 July 2026. Eight published regional
  labels remain branch/channel attribution under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,499 appearances**, **294,728 address
  records**, **10,771 partial records** and **297,872 dated appearances inside
  the current 20-year window**, including **102,024 guide-price records** and
  **111,507 achieved-price records**. The surviving-complete catalogue count is
  3,820; 515 remain incomplete or unreconciled and 22 have fetch/parse errors.
  National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/83949?lotResultType=All`,
  dated 4 August 2026. Its archive index exposes **46 individual cards**.
  Reconcile the published denominator, every stable source identity and every
  detail page; bank immutable evidence and exclude only exact overlaps before
  claiming growth. Do not revisit terminal events 69595, 79607 or 82154 without
  a materially different recovery route. National completeness remains false.


## 28 October 2026 — Auction House Online 4 August event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/83949?lotResultType=All`.
  Discovery had exposed 46 cards, but the live archive now publishes and
  exposes **45 cards**. The denominator guard rejected the stale 46-card
  expectation before accepting the current inventory. All 45 visible cards,
  stable source identities and detail pages reconcile exactly; the disappeared
  card was not manufactured or counted.
- Admitted **8 net-new appearances and address records**, all dated inside the
  current 20-year window. Thirty-seven exact date/address overlaps with
  existing regional evidence were audited and excluded, with no duplicate
  source identities, partial, undated or future-dated additions.
- Added **8 guide-price records**, **zero achieved-price records** and **zero
  rent values**. The evidence-based sector split is five residential, two land
  and one unknown; commercial/mixed-use growth is **zero**. Outcomes remain
  distinct: four postponed, one sold-prior, two withdrawn and one unsold.
- Preserved individual dates from 29 July to 4 August 2026. Auction House South
  West, Wales - Colwyn Bay, London and Kent remain branch attribution under
  **AUCTION HOUSE UK LIMITED (company 06025583)** rather than new legal
  operators.
- The rebuilt corpus contains **305,507 appearances**, **294,736 address
  records**, **10,771 partial records** and **297,880 dated appearances inside
  the current 20-year window**, including **102,032 guide-price records** and
  **111,507 achieved-price records**. The surviving-complete catalogue count is
  3,824; 515 remain incomplete or unreconciled and 22 have fetch/parse errors.
  National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/83905?lotResultType=All`.
  The live archive index exposes **72 cards for 11 August 2026** (its
  description incorrectly says 2025). Require the published denominator,
  every stable source identity and every detail page before banking evidence,
  and exclude only exact overlaps. National completeness remains false.


## 29 October 2026 — Auction House Online 11 August event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/83905?lotResultType=All`.
  Its **72 visible result cards**, 72 stable source identities and 72 detail
  pages reconcile exactly against the published 72-lot denominator; immutable
  index and lot snapshots were banked.
- Admitted **11 net-new appearances and address records**, all dated inside the
  current 20-year window. Sixty-one exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **11 guide-price records**, **zero achieved-price records** and **three
  rent values**. The evidence-based sector split is seven residential and four
  unknown appearances; commercial/mixed-use growth is **zero commercial and
  zero mixed-use**. Outcomes remain distinct: three postponed, six withdrawn
  and two unsold.
- Preserved individual dates from 22 July to 11 August 2026. Eight published
  regional/channel labels remain branch attribution under **AUCTION HOUSE UK
  LIMITED (company 06025583)** rather than additional legal operators.
- A later protected bounded rotation added **15 separate Phillip Arnold
  Auctions appearances**. Those records are not included in the focused event
  metrics above. The resulting corpus contains **305,533 appearances**,
  **294,762 address records**, **10,771 partial records** and **297,932 dated
  appearances inside the current 20-year window**, including **102,054
  guide-price records** and **111,507 achieved-price records**. The
  surviving-complete catalogue count is 3,831; 515 remain incomplete or
  unreconciled and 22 have fetch/parse errors. National completeness remains
  false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84252?lotResultType=All`,
  dated 18 August 2026 and currently exposing **59 individual cards**. Require
  the published denominator, every stable source identity and every detail
  page; preserve dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, and exclude only exact date/address overlaps.
  Auction House regional labels remain attribution under AUCTION HOUSE UK
  LIMITED. National completeness remains false.


## 29 October 2026 — Auction House Online 18 August event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/84252?lotResultType=All`.
  Its **59 visible result cards**, 59 stable source identities and 59 detail
  pages reconcile exactly against the published 59-lot denominator; immutable
  index and lot snapshots were banked.
- Admitted **6 net-new appearances and address records**, all dated inside the
  current 20-year window. Fifty-three exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **6 guide-price records**, **zero achieved-price records** and **zero
  rent values**. The evidence-based sector split is two residential and four
  unknown appearances; commercial/mixed-use growth is **zero commercial and
  zero mixed-use**. Outcomes remain distinct: five sold-prior and one unsold.
- Preserved individual dates from 29 July to 18 August 2026. Five published
  regional/channel labels remain branch attribution under **AUCTION HOUSE UK
  LIMITED (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,539 appearances**, **294,768 address
  records**, **10,771 partial records** and **297,938 dated appearances inside
  the current 20-year window**, including **102,060 guide-price records** and
  **111,507 achieved-price records**. Undated is 4,395 and future-dated is 163.
  Surviving-complete catalogue states increased to **3,837**; 515 remain
  incomplete or unreconciled and 22 have fetch/parse errors. The workflow
  test stages passed 393 and 128 tests. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84203?lotResultType=All`,
  dated 25 August 2026 and currently exposing **92 individual cards**. Require
  the published denominator, every stable source identity and every detail
  page; preserve dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, and exclude only exact date/address overlaps.
  Auction House regional labels remain attribution under AUCTION HOUSE UK
  LIMITED. National completeness remains false.


## 29 October 2026 — Auction House Online 25 August event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/84203?lotResultType=All`.
  Its **92 visible result cards**, 92 stable source identities and 92 detail
  pages reconcile exactly against the published 92-lot denominator; immutable
  index and lot snapshots were banked.
- Admitted **19 net-new appearances and address records**, all dated inside the
  current 20-year window. Seventy-three exact date/address overlaps with
  existing regional evidence were audited and excluded, with no duplicate
  source identities, partial, undated or future-dated additions.
- Added **19 guide-price records**, **zero achieved-price records** and **one
  rent value**. The evidence-based sector split is 14 residential, three
  unknown, one commercial and one land appearance; commercial/mixed-use growth
  is **one commercial and zero mixed-use**. Outcomes remain distinct: nine
  postponed, five withdrawn and five sold-prior.
- Preserved individual property dates from 7 to 24 August 2026. Thirteen
  published regional/channel labels remain branch attribution under **AUCTION
  HOUSE UK LIMITED (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,558 appearances**, **294,787 address
  records**, **10,771 partial records** and **297,957 dated appearances inside
  the current 20-year window**, including **102,079 guide-price records** and
  **111,507 achieved-price records**. Undated is 4,395 and future-dated is 163.
  Surviving-complete catalogue states increased to **3,841**; 515 remain
  incomplete or unreconciled and 22 have fetch/parse errors. The workflow test
  stages passed 394 and 128 tests. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84567?lotResultType=All`,
  dated 8 September 2026 and currently exposing **73 individual cards**. It is
  prioritised over the smaller 17-card 2 September event 84329, which remains
  queued rather than treated as covered. Require the published denominator,
  every stable source identity and every detail page; preserve dates, guides,
  achieved prices, rents, outcomes, original URLs and immutable snapshots, and
  exclude only exact date/address overlaps. Auction House regional labels
  remain attribution under AUCTION HOUSE UK LIMITED. National completeness
  remains false.

## 29 October 2026 — Auction House Online 8 September event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/84567?lotResultType=All`.
  Its **73 visible result cards**, 73 stable source identities and 73 detail
  pages reconcile exactly against the published 73-lot denominator; immutable
  index and lot snapshots were banked.
- Admitted **12 net-new appearances and address records**, all dated inside the
  current 20-year window. Sixty-one exact date/address overlaps with existing
  regional evidence were audited and excluded, with no duplicate source
  identities, partial, undated or future-dated additions.
- Added **12 guide-price records**, **three achieved-price records** and **zero
  rent values**. The evidence-based sector split is 11 residential and one
  unknown appearance; commercial/mixed-use growth is **zero commercial and zero
  mixed-use**. Outcomes remain distinct: six sold-prior, three postponed and
  three withdrawn.
- Preserved individual property dates from 4 August to 7 September 2026. Six
  published regional/channel labels remain branch attribution under **AUCTION
  HOUSE UK LIMITED (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,570 appearances**, **294,799 address
  records**, **10,771 partial records** and **297,969 dated appearances inside
  the current 20-year window**, including **102,091 guide-price records** and
  **111,510 achieved-price records**. Undated is 4,395 and future-dated is 163.
  Surviving-complete catalogue states increased to **3,848**; 515 remain
  incomplete or unreconciled and 22 have fetch/parse errors. The workflow test
  stages passed 395 and 128 tests. Production publication and permanent-history
  banking completed successfully. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84327?lotResultType=All`,
  dated 29 September 2026 and currently exposing **98 of 98 individual cards**.
  It is prioritised as the largest verified September opportunity; the smaller
  17-card 2 September event 84329 and the intervening 15 and 22 September events
  remain queued rather than treated as covered. Require the published
  denominator, every stable source identity and every detail page; preserve
  dates, guides, achieved prices, rents, outcomes, original URLs and immutable
  snapshots, and exclude only exact date/address overlaps. Auction House
  regional labels remain attribution under AUCTION HOUSE UK LIMITED. National
  completeness remains false.

## 29 October 2026 — Auction House Online 29 September event reconciled

- Collected first-party event
  `https://online.auctionhouse.co.uk/past-auctions/84327?lotResultType=All`.
  Its **98 visible result cards**, 98 stable source identities and 98 detail
  pages reconcile exactly against the published 98-lot denominator; immutable
  index and lot snapshots were banked.
- Admitted **20 net-new appearances and address records**, all dated inside the
  current 20-year window. Seventy-eight exact date/address overlaps with
  existing regional evidence were audited and excluded, with no duplicate
  source identities, partial, undated or future-dated additions.
- Added **20 guide-price records**, **one achieved-price record** and **zero rent
  values**. The evidence-based sector split is 16 residential, three unknown
  and one land appearance; commercial/mixed-use growth is **zero commercial
  and zero mixed-use**. Outcomes remain distinct: nine postponed, six
  sold-prior, four withdrawn and one sold.
- Preserved individual property dates from 3 to 29 September 2026. Eleven
  published regional/channel labels remain branch attribution under **AUCTION
  HOUSE UK LIMITED (company 06025583)** rather than additional legal operators.
- The rebuilt corpus contains **305,590 appearances**, **294,819 address
  records**, **10,771 partial records** and **297,989 dated appearances inside
  the current 20-year window**, including **102,111 guide-price records** and
  **111,511 achieved-price records**. Undated is 4,395 and future-dated is 163.
  Surviving-complete catalogue states increased to **3,857**; 515 remain
  incomplete or unreconciled and 22 have fetch/parse errors. The workflow test
  stages passed 396 and 128 tests. Production publication and permanent-history
  banking completed successfully. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/85650?lotResultType=All`,
  dated 27 October 2026 and currently exposing **125 of 125 individual cards**.
  It is prioritised as the largest verified remaining opportunity; the smaller
  outstanding September events and the 6, 13 and 20 October events remain
  queued rather than treated as covered. Require the published denominator,
  every stable source identity and every detail page; preserve dates, guides,
  achieved prices, rents, outcomes, original URLs and immutable snapshots, and
  exclude only exact date/address overlaps. Auction House regional labels
  remain attribution under AUCTION HOUSE UK LIMITED. National completeness
  remains false.

## 29 October 2026 — Auction House Online 27 October event blocked before inventory

- Targeted the first-party all-results catalogue at
  `https://online.auctionhouse.co.uk/past-auctions/85650?lotResultType=All`.
  The official event detail reports **125 lots for 27 October 2026**, making it
  the largest verified remaining opportunity at the start of this run.
- The collector made five bounded archive-index requests. Each exhausted a
  120-second read timeout before the response body could be parsed. The failure
  occurred before card inventory, stable identities, detail pages or an
  immutable index snapshot could be reconciled; no second collector was
  launched and no captured evidence was discarded.
- This is a genuine **zero-growth** attempt: **0 net-new appearances**, **0 new
  address records**, **0 newly dated address records inside the 20-year
  window**, **0 commercial/mixed-use records**, **0 source-years**, **0 legal
  operator-years**, **0 guides**, **0 achieved prices** and **0 rents**. There
  were no partial, undated, future-dated or duplicate additions. Overlaps are
  unmeasured because the source inventory was not retrieved; zero exclusions
  must not be read as proof that no overlaps exist.
- The normal saved-corpus bank, rebuild, source-register reconciliation and
  protected checkpoint completed. Corpus totals remain **305,590
  appearances**, **294,819 address records**, **10,771 partial records** and
  **297,989 dated appearances inside the current 20-year window**, including
  **102,111 guide-price records** and **111,511 achieved-price records**.
  Surviving-complete catalogues remain **3,857**; 515 are incomplete or
  unreconciled and 22 have fetch/parse errors. Validation passed **397 and 128
  tests**. Permanent-history banking and publication validation completed
  successfully. National completeness remains false.
- Treat event 85650's current all-results route as blocked until the upstream
  response changes or a materially different retrieval route exists. **Next
  concrete growth target:** collect
  `https://online.auctionhouse.co.uk/past-auctions/85651?lotResultType=All`,
  whose first-party event detail and archive index report **87 of 87 lots for
  20 October 2026**. Event 85028 (86 lots, 13 October 2026) is the secondary
  target; smaller September and 6 October events remain queued, not covered.
  Require the published denominator, stable source identities and detail-page
  reconciliation before claiming growth, and keep regional labels as branch
  attribution under AUCTION HOUSE UK LIMITED.

## 29 October 2026 — Auction House Online 20 October visible inventory banked, catalogue partial

- Collected the first-party all-results event at
  `https://online.auctionhouse.co.uk/past-auctions/85651?lotResultType=All`.
  The official event detail and archive index advertise **87 lots**, but the
  live all-results page exposes an internally consistent denominator of **86
  visible result cards**. All 86 stable source identities and 86 detail pages
  were captured with immutable index and lot snapshots. The one-row published
  discrepancy remains explicit; this catalogue is not complete.
- Admitted **17 net-new appearances and address records**, all dated inside the
  current 20-year window. Sixty-nine exact date/address overlaps with existing
  regional evidence were audited and excluded. There were no duplicate source
  identities and no partial, undated or future-dated additions.
- Added **17 guide-price records**, **zero achieved-price records** and **one
  rent value**. The evidence-based sector split is 12 residential, one
  commercial, one land, one mixed-use and two unknown appearances;
  commercial/mixed-use growth is therefore **one commercial and one
  mixed-use**. Outcomes remain distinct: nine postponed, five withdrawn, one
  sold-prior and two unsold.
- Preserved individual property dates from 6 to 20 October 2026. Auction House
  South Yorkshire, Kent, London, North East, Birmingham and Online remain
  branch/channel attribution under **AUCTION HOUSE UK LIMITED (company
  06025583)** rather than new legal operators. The event adds one evidenced
  source-year and zero legal operator-years.
- The rebuilt corpus contains **305,607 appearances**, **294,836 address
  records**, **10,771 partial records** and **298,006 dated appearances inside
  the current 20-year window**, including **102,128 guide-price records** and
  **111,511 achieved-price records**. Undated is 4,395 and future-dated is 163.
  Surviving-complete catalogue states correctly remain **3,857**; 522 are
  incomplete or unreconciled and 22 have fetch/parse errors. The collector's
  per-date states were corrected so internally reconciled visible rows do not
  falsely turn the 87-versus-86 event into a complete catalogue. Validation
  passed **399 and 128 tests**. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/85028?lotResultType=All`,
  whose official event detail and archive index advertise **86 lots for 13
  October 2026**. Smaller outstanding September and 6 October events remain
  queued, not covered. Reconcile the advertised denominator, visible inventory,
  stable identities and detail pages; preserve a partial state if they differ,
  preserve all dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, and exclude exact date/address overlaps before
  claiming growth. Regional labels remain branch attribution under AUCTION
  HOUSE UK LIMITED.

## 29 October 2026 — Auction House Online 13 October visible inventory banked, catalogue partial

- Collected the first-party all-results event at
  `https://online.auctionhouse.co.uk/past-auctions/85028?lotResultType=All`.
  The official event detail advertises **87 lots**, but the GitHub runner's
  live all-results response exposes a self-consistent **86 visible result
  cards**. All 86 stable source identities and 86 detail pages were captured
  with immutable index and lot snapshots. The one-row discrepancy remains
  explicit; this catalogue is not complete.
- Admitted **20 net-new appearances and address records**, all individually
  dated from 5 to 12 October 2026 and inside the current 20-year window.
  Sixty-six exact date/address overlaps with existing regional evidence were
  audited and excluded. There were no duplicate source identities and no
  partial, undated or future-dated additions.
- Added **20 guide-price records**, **zero achieved-price records** and **zero
  rent values**. The evidence-based sector split is 15 residential and five
  unknown appearances, with **zero commercial or mixed-use additions**.
  Outcomes remain distinct: 12 postponed, six sold-prior and two withdrawn.
- Auction House South Yorkshire, Coventry and Warwickshire, North East, Kent,
  Northants Beds & Bucks, North West and Hull & East Yorkshire remain
  branch/channel attribution under **AUCTION HOUSE UK LIMITED (company
  06025583)** rather than new legal operators. The event adds one evidenced
  source-year and zero legal operator-years.
- The rebuilt corpus contains **305,627 appearances**, **294,856 address
  records**, **10,771 partial records** and **298,026 dated appearances inside
  the current 20-year window**, including **102,148 guide-price records** and
  **111,511 achieved-price records**. Undated remains 4,395 and future-dated
  remains 163. Surviving-complete catalogue states remain **3,857**; 529 are
  incomplete or unreconciled and 22 have fetch/parse errors. Collection,
  publication, permanent-history banking, Pages deployment and custom-domain
  deployment all completed successfully. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84253?lotResultType=All`,
  whose results surface currently exposes **87 of 87 lots for 22 September
  2026**. The smaller 15 September and 6 October catalogues remain queued, not
  covered. Reconcile the published denominator, visible inventory, stable
  identities and detail pages; preserve a partial state if they differ,
  preserve all dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, and exclude exact date/address overlaps before
  claiming growth. Regional labels remain branch attribution under AUCTION
  HOUSE UK LIMITED.

## 29 October 2026 — Auction House Online 22 September catalogue fully reconciled

- Collected the first-party all-results event at
  `https://online.auctionhouse.co.uk/past-auctions/84253?lotResultType=All`.
  The archive index, live grid, stable source identities and detail-page
  inventory all reconcile at **87 of 87 rows**. Immutable index and lot
  snapshots were retained and this catalogue is complete.
- Admitted **10 net-new appearances and address records**, all individually
  dated from 18 to 22 September 2026 and inside the current 20-year window.
  Seventy-seven exact date/address overlaps with existing regional evidence
  were audited and excluded. There were no duplicate source identities and no
  partial, undated or future-dated additions.
- Added **10 guide-price records**, **three achieved-price records** and **zero
  rent values**. The evidence-based sector split is seven residential, one land
  and two unknown appearances, with **zero commercial or mixed-use additions**.
  Outcomes remain distinct: six postponed, three sold-prior and one sold.
- Auction House London, West Yorkshire, Online, South Yorkshire, North West,
  Coventry and Warwickshire, Birmingham and Wales - Colwyn Bay remain
  branch/channel attribution under **AUCTION HOUSE UK LIMITED (company
  06025583)** rather than new legal operators. The event adds one evidenced
  source-year and zero legal operator-years.
- The rebuilt corpus contains **305,637 appearances**, **294,866 address
  records**, **10,771 partial records** and **298,036 dated appearances inside
  the current 20-year window**, including **102,158 guide-price records** and
  **111,514 achieved-price records**. Undated remains 4,395 and future-dated
  remains 163. Surviving-complete catalogue states increased to **3,860**; 529
  remain incomplete or unreconciled and 22 have fetch/parse errors. Collection,
  publication validation and permanent-history banking completed successfully.
  The downstream public-platform foundation run was cancelled by its existing
  concurrency control before a job started; that checkpoint was preserved and
  no duplicate deployment was launched. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84412?lotResultType=All`,
  whose archive index publishes **71 result rows for 15 September 2026**.
  Lot numbering reaches 72 because the numbering has a gap and must not be used
  as the denominator. The 46-row 6 October catalogue remains queued, not
  covered. Reconcile the published row denominator, visible inventory, stable
  identities and detail pages; preserve a partial state if they differ,
  preserve all dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, and exclude exact date/address overlaps before
  claiming growth. Regional labels remain branch attribution under AUCTION
  HOUSE UK LIMITED.

## 29 October 2026 — Auction House Online 15 September catalogue fully reconciled

- Collected the first-party all-results event at
  `https://online.auctionhouse.co.uk/past-auctions/84412?lotResultType=All`.
  The archive index, live grid, stable source identities and detail-page
  inventory all reconcile at **71 of 71 rows**. The apparent lot-number extent
  of 72 contains a numbering gap and was not used to invent a missing row.
  Immutable index and lot snapshots were retained and this catalogue is
  complete.
- Admitted **15 net-new appearances and address records**, all individually
  dated from 20 August to 15 September 2026 and inside the current 20-year
  window. Fifty-six exact date/address overlaps with existing regional evidence
  were audited and excluded. There were no duplicate source identities and no
  partial, undated or future-dated additions.
- Added **15 guide-price records**, **zero achieved-price records** and **one
  rent value**. The evidence-based sector split is 12 residential, one land and
  two unknown appearances, with **zero commercial or mixed-use additions**.
  Outcomes remain distinct: five sold-prior, four postponed, three withdrawn
  and three unsold.
- Auction House East Anglia, London, Wales - Cardiff, North East, Hull & East
  Yorkshire, Cheshire Staffordshire & Shropshire, South Yorkshire, West
  Yorkshire and Wales - Colwyn Bay remain branch/channel attribution under
  **AUCTION HOUSE UK LIMITED (company 06025583)** rather than new legal
  operators. The event adds one evidenced source-year and zero legal
  operator-years.
- The rebuilt corpus contains **305,652 appearances**, **294,881 address
  records**, **10,771 partial records** and **298,051 dated appearances inside
  the current 20-year window**, including **102,173 guide-price records** and
  **111,514 achieved-price records**. Undated remains 4,395 and future-dated
  remains 163. Surviving-complete catalogue states increased to **3,866**; 529
  remain incomplete or unreconciled and 22 have fetch/parse errors. The
  workflow test stages passed 403 and 128 tests. Collection, database rebuild,
  publication revalidation, Pages validation and permanent-history banking
  completed successfully. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/85376?lotResultType=All`.
  Its all-results route exposes **46 of 46 visible rows for 6 October 2026**,
  while the separate event detail advertises 47 lots. Bank every evidenced
  visible row, but preserve the one-row discrepancy and do not claim catalogue
  completeness unless a materially different route recovers the missing lot.
  The complete 17-row 2 September event 84329 remains queued second rather than
  treated as covered. Reconcile every visible stable source identity and detail
  page, preserve dates, guides, achieved prices, rents, outcomes, original URLs
  and immutable snapshots, exclude exact date/address overlaps before claiming
  growth, and keep regional labels as branch attribution under AUCTION HOUSE UK
  LIMITED.

## 29 October 2026 — Auction House Online 6 October visible inventory banked

- Collected the first-party all-results event at
  `https://online.auctionhouse.co.uk/past-auctions/85376?lotResultType=All`.
  The results route reconciles **46 visible cards, 46 stable source identities
  and 46 detail pages**, with immutable index and lot snapshots retained. The
  separate event detail advertises 47 lots, so the missing row remains an
  explicit blocker and this catalogue is **not** marked complete.
- Admitted **nine net-new appearances and address records**, all individually
  dated from 14 September to 6 October 2026 and inside the current 20-year
  window. Thirty-seven exact date/address overlaps with existing regional
  evidence were audited and excluded. There were no duplicate source
  identities and no partial, undated or future-dated additions.
- Added **nine guide-price records**, **zero achieved-price records** and
  **zero rent values**. The evidence-based sector split is seven residential
  and two unknown appearances, with **zero commercial or mixed-use additions**.
  Outcomes remain distinct: five postponed, two sold-prior, one withdrawn and
  one unsold.
- Auction House South Yorkshire, Birmingham, East Anglia, Kent and Hull & East
  Yorkshire remain branch/channel attribution under **AUCTION HOUSE UK LIMITED
  (company 06025583)** rather than new legal operators. The event adds one
  evidenced source-year and zero legal operator-years.
- The rebuilt corpus contains **305,661 appearances**, **294,890 address
  records**, **10,771 partial records** and **298,060 dated appearances inside
  the current 20-year window**, including **102,182 guide-price records** and
  **111,514 achieved-price records**. Undated remains 4,395 and future-dated
  remains 163. Surviving-complete catalogue states remain **3,866**; 535 are
  incomplete or unreconciled and 22 have fetch/parse errors. Focused tests
  passed 104/104. Collection, database rebuild, publication revalidation,
  Pages/custom-domain deployment and permanent-history banking completed
  successfully. National completeness remains false.
- **Next concrete growth target:** collect first-party Auction House Online
  event `https://online.auctionhouse.co.uk/past-auctions/84329?lotResultType=All`,
  whose results route exposes **17 of 17 rows for 2 September 2026**. Reconcile
  every visible stable identity and detail page, preserve all dates, guides,
  achieved prices, rents, outcomes, original URLs and immutable snapshots,
  and exclude exact date/address overlaps before claiming growth. Do not retry
  event 85376's same incomplete route unless a materially different recovery
  path emerges.
