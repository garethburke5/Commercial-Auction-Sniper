# Allsop post-auction availability correction — 17 October 2026

Reported lot: 182 & 182a Barrack Road, Christchurch, Dorset, BH23 2BQ, lot 77, reference C261001 215.

The 17 October 11:09 UTC production snapshot retained this lot in `archive`, with status WITHDRAWN and a 7 October collection timestamp. The live official exact-lot API and 7 October catalogue now both report Available, with a £575,000 guide and £53,800 annual rent.

Evidence:
- https://www.allsop.co.uk/lot-overview/freehold-restaurant-takeaway-residential-investment-in-christchurch/c261001-215
- https://www.allsop.co.uk/api/lot/reference/c261001-215
- https://www.allsop.co.uk/api/search?auction_id=15cddc4c-34b8-11f1-99af-0242ac110002&size=100&page=1

Two independent causes:
1. The collector fetched only the next commercial and residential catalogues. It never rechecked the recent auction after its date passed.
2. Both publication lifecycle and homepage search excluded past auction dates, even if the auctioneer still offered a property for sale.

Correction:
- Reconcile upcoming catalogues plus the previous 60 days of commercial and residential auctions, retaining the existing commercial/mixed-use admission checks and complete pagination.
- Read current availability from the exact lot response, recording its check time. Missing detail status cannot establish availability.
- Permit past-dated Allsop lots only with explicit Available/Unsold/For Sale evidence checked within 14 hours. Sold/withdrawn and stale evidence remain excluded.
- Do not carry old availability forward when a new response omits it.
- Keep the original auction date, property identity, URL and historical records. Display “Available after auction” beside the original date.

This fixes recent post-auction marketing, not full historical Allsop recovery. Older than 60-day catalogues remain outside this current collection scope.

Verification before publication: collector regression suite (837 tests plus 8 subtests), and five focused regressions covering stale/missing evidence, sold/withdrawn exclusion, corrected withdrawal, catalogue scope and public search inclusion. A live full Allsop reconciliation is also running; deployed publication must be checked after the automatic production scan/build completes.
