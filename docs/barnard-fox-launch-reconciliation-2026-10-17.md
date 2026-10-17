# Barnard Marcus / Fox & Sons — launch reconciliation, 17 October 2026

## Correction and evidence

The existing collector selected only future auction dates. The first-party upcoming page also links to the latest result catalogue and its available lots. Discovery now covers those advertised dates, limited to the latest past catalogue plus upcoming dates; it does not crawl the historic auction archive. Canonical URLs are deduplicated and restricted to the first-party host.

The source's own public catalogue API is discovered from the page configuration, using its published available filter and pagination. An old guide price never proves availability. Exact positive available/unsold statuses receive a timestamp and use the existing 14-hour freshness control. Sold/withdrawn detail-page outcomes take precedence. Pagination, duplicates, foreign hosts, inconsistent counts and missing details remain visible in source health. No authoritative-completeness claim is made.

The targeted run used first-party HTML/JSON captured this evening, cached locally to avoid repeat requests while checking the parser. It completed in 416 seconds:

| Measure | Observed |
| --- | ---: |
| Advertised dates | 15 October and 17 November 2026 |
| Detail URLs discovered | 363 |
| Details parsed | 361 |
| Details missing particulars | 2 |
| Commercial candidates before publication gate | 20 |
| Candidates passing the tightened publication gate | 11 |
| Eligible withdrawn / sold / sold-prior records | 4 / 4 / 1 |
| Eligible records without a terminal result | 2 |
| Eligible past-auction lot with explicit fresh availability | 1 |

The available feed reports 137 rows but returns 135 unique cards across nine pages. Of those, 84 explicitly say available/unsold; Draft is not treated as availability. Source health stays DEGRADED. Missing-particulars URLs:

- https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/724850/
- https://www.barnardmarcusauctions.co.uk/auctions/17-november-2026/730657/

## Fox & Sons and classification

All 22 exact Barnard Marcus lot links on the Fox & Sons homepage occur in the canonical discovery set. Two have qualifying commercial/mixed-use particulars: lot 167 (withdrawn car-parking investment) and lot 170 (Northwood Road mixed-use property).

Lot 167's existing car-parking tenancy now qualifies without a duplicate Fox collector. Its published one-third-acre area is no longer incorrectly read as three acres; fractional acreage parsing preserves source-specific values. Residential parking and merely proposed commercial use are not enough.

Real-record review additionally excluded land adjoining a hotel, a former pub undergoing residential development, and a home whose care-home use would need reinstatement. Mentioning a neighbouring or former commercial use is not current investment evidence. Existing mixed-use premises remain eligible despite additional residential planning.

Fox's homepage labels lot 170 unsold, whereas the canonical availability feed does not provide the accepted positive status. This conflict remains a reconciliation item: no availability is invented from its guide price. Neither the 22-link match nor these changes sign off complete Fox brand filtering or the separate modern-method iamsold channel.

## Validation and deployment boundary

852 collector regression tests and 19 subtests pass locally after the classification corrections. Coverage includes partial source counts, incorrect hosts, duplicate pagination, availability failure, terminal-status precedence, withdrawn retention, fractions and residential exclusions.

Discovery/availability correction commit: `33429ca43c30c6f5e200f52e850974efff086318`. Production collection run `39066080736` was still running when this note was written. The local source result is not a claim that refreshed lots have reached the live website. The existing workflow must finish collection, validation and public publication before that is accepted.

First-party references: https://www.barnardmarcusauctions.co.uk/auctions/upcoming/ ; https://www.barnardmarcusauctions.co.uk/auctions/15-october-2026/ ; https://www.foxandsonsauctions.co.uk/
