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
