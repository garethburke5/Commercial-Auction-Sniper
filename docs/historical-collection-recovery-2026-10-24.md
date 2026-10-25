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
