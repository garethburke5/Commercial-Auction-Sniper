# Separate related property interests from exact historical matches

## Why Newbury was missed

The earlier record already existed in the archive. The public/private MarketContext matcher only admitted exact address strings or a conservative numbered-street/locality alias with matching tenure. The additional `1 The Arcade` address and Freehold → Leasehold change excluded it. There was no separate relationship channel.

A second problem was stale archive evidence: the Allsop archive retained `available`, no sale price and a 1 October reference-code date. The newer catalogue had the published 7 October event and `SOLD`, but its collector discarded the source's sale price. Allsop's public search API now reports £190,000 sold; its lot-detail API confirms 7 October. This is labelled a reported sale, not verified completion.

## Reusable implementation

- Match building candidates using an exact postcode plus explicit numbered street components, or recorded title identifiers. Keep unit, building and floor qualifiers when assessing exact matches. Never merge auction/property records or entitlement identities.
- Classify different legal interests, title identifiers, unit schedules, new lease terms and recorded floor areas separately. Ambiguous address scope remains a related candidate, not an exact asset match.
- Link compound addresses to their components. Do not infer all intermediate numbers in a street range or merge neighbouring suffix addresses.
- Include residential archive records in building relationship discovery, while retaining commercial comparable filters.
- Exclude related offerings from comparable selection and guide/rent change calculations.
- Reconcile newer captures only for the same source URL, lot and nearby event date; preserve older archive observations. Keep source result status and sale price separate from the guide.
- Public previews disclose the existence of related offerings. Detailed addresses, prices, rent, accommodation and original source links appear after the existing server-side entitlement check. The subscription/single-property/day-pass rules and sales gates are unchanged.
- Allsop's collector now retains explicitly reported sale prices. Historical conversion no longer mistakes `unsold` for `sold` by substring.

## Newbury source checks

- Savills lot 107, 3 November: 150–151 Bartholomew Street, £150,000 guide, £20,000 annual rent, 993 sq ft, a new 999-year lease at peppercorn rent.
- Allsop lot 64, 7 October: 150–151 Bartholomew Street **and 1 The Arcade**, larger freehold offering, £190,000–£200,000 guide, £26,700 annual rent, 1,204 sq ft. Source reports sold for £190,000.
- The retained tenancy schedule also identifies the two flats sold on long leases, each producing £100 ground rent.
- Savills is separately advertising 1 The Arcade: £20,000 guide, £6,500 rent, new 999-year lease. It links to the larger offering too.
- None of these facts establish a completed transfer or title genealogy. No price reduction is calculated between the separate offerings.

Sources:
- https://auctions.savills.co.uk/auctions/3-november-2026-245/150-151-bartholomew-street-newbury-berkshire-rg14-5hb-25826
- https://auctions.savills.co.uk/auctions/3-november-2026-245/1-the-arcade-newbury-berkshire-rg14-5hb-25827
- https://www.allsop.co.uk/lot-overview/grade-ii-listed-freehold-retail-units-and-residential-ground-rent-investment-in-newbury/c261001-003
- https://www.allsop.co.uk/api/lot/reference/c261001-003
- https://www.allsop.co.uk/api/search?auction_id=15cddc4c-34b8-11f1-99af-0242ac110002&size=1000&page=1

## Verification

The read-only check covered 904 current catalogue listings against the retained archive: 352 candidate pairs and 42 related offerings across 21 listings. These are recorded relationship candidates, not 21 independently confirmed subdivisions. Formatting/extent uncertainty is retained explicitly. Actual holdouts include 57 Northgate versus 57–67 Northgate (Darlington), Unit 4 versus Units 1–3 Pydar Street (Truro), separate Fore Street units (Chard), and Queen Street units (Barnsley).

Run `PYTHONPATH=. python scripts/check_related_property_interests.py --output /tmp/related-property-check.json` to repeat against the current catalogue and archive. Tests cover source-backed Newbury and holdouts, adjacent addresses/postcodes, unit/floor splits, title changes, regranted leases, status labels, guide/rent comparison suppression and premium API isolation. Browser regression renders the real Newbury relationship panel at 390px and 1440px.

Local platform regression: 359 passed, 14 skipped before the final related-scope refinements; focused relationship/access/collector checks passed afterwards. Production build, browser and live checks are recorded in the delivery update rather than assumed from local tests.
