# Property address search improvements — 26 October 2026

## Objective

Improve the discoverability and search presentation of ordinary Auction Geek
property listings, not only the Newbury and Percy Street case studies. No paid
advertising, paid AI requests, synthetic reviews or fabricated property facts.

## User's Google baseline

These are owner-observed positions, not an automated or neutral ranking survey.

| Address | Observed result |
| --- | --- |
| 150–151 Bartholomew Street, Newbury | Page 1, position 8 |
| 15–23 Percy Street, Stoke-on-Trent | Page 2, first result |
| 1 Hamel House, Calico Business Park, Tamworth B77 4BF | Not found |
| 1 Nutter Road, Thornton-Cleveleys FY5 1BG | Not found |
| 103 Hilderthorpe Road, Bridlington YO15 3BH | Page 6 |
| 15 Bridgewater Road, Worsley M28 3JE | Page 1, position 10 |

Search retrieval also found Hamel House and Nutter Road snapshots. This is not
proof of their Google indexing status, nor a contradiction of the owner's search.
The stored 10:54 catalogue already admitted the four ordinary examples under the
previous indexing rule. The broader indexing fix is not asserted to explain their
individual rankings.

## Changes

- Keep the complete property address and postcode in the title; identify the page
  as auction details without describing a withdrawn or historical lot as for sale.
- Replace generic source/type-only descriptions with the exact address, guide
  price (including ranges), auctioneer, date where known, and available research.
  Withdrawn/sold lots carry their status and a recorded-guide label. No assumed
  current rent, yield, valuation or completed sale is added to search metadata.
- Include linked Properties and Auctioneer breadcrumbs, with matching structured
  breadcrumb data, plus the public property's address and photograph in schema.
- Permit large search image previews. This is permission, not a rich-result promise.
- Remove auction date as a compulsory indexing condition. Substantial particulars
  with a positive guide price can qualify without rent/tenure fields. Short text,
  missing useful facts and addresses replaced by long marketing copy remain excluded.
- Keep premium-history protection, private APIs, snapshot eligibility and canonical
  property URLs unchanged. No new thin location pages or duplicate property URLs.
- Check rendered HTML on every export: exact-address title/description, canonical,
  robots directive, sitemap admission, and a crawlable link path from the homepage.
  Fail publication on contradictions. Save `public-dist-search-audit.json` outside
  the public export and retain it as the `property-search-audit` Actions artifact.

## Verification

- Focused regression suite: 69 tests covering SEO, platform routes, premium access,
  snapshots, sharing and Cloudflare export.
- Full local render against the stored 26 October 10:54:48 UTC publication candidate:
  2,273 distinct property pages; 2,146 eligible for indexing versus 1,684 under the
  old rule; zero rendered-page search-check failures. These are local eligibility
  counts, not current live totals or Google's indexed-page counts.
- Thin-page and private-account noindex behaviour remains covered by tests.
- Tests deliberately introduce an incorrect canonical, accidental noindex and an
  orphaned property page and confirm that the export audit detects them.

## Deployment and measurement still required

The Cloudflare Workers build for the pre-change main commit
`4a2e219d15b9292ed3a61ce449b7925a9243fd18` failed. GitHub Pages deployment is separate
and does not establish that auctiongeek.co.uk has received these changes.

After the custom-domain deployment is restored, verify live HTML, robots and sitemap.
Use Google Search Console to inspect the six URLs and Google's selected canonicals,
submit/check the sitemap, and request recrawling where appropriate. Search Console
verification/access was not established during this change. Measure page/query
impressions, clicks and average positions, retaining the ordinary-property cohort.
Do not claim improved Google positions until measured after deployment and recrawl.

Useful content, accurate source data and earned external links remain ongoing work;
metadata alone does not establish authority or guarantee rankings.

References: Google Search Central documentation on
[title links](https://developers.google.com/search/docs/appearance/title-link),
[snippets](https://developers.google.com/search/docs/appearance/snippet), and
[sitemaps](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview).
