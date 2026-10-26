# Keep the GitHub Pages mirror out of search — 26 October 2026

Successful public-platform run
[40344029082](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/40344029082)
confirmed 489 tests passed, 14 skipped, 3 subtests passed; desktop/mobile browser
checks passed; 4,744 public pages exported; 1,073 expected searchable properties
matched the deployed GitHub Pages copy. The source report still records 36 degraded
sources. This is not proof of successful deployment to auctiongeek.co.uk.

The run also confirmed that GitHub Pages renders under its own github.io origin.
Previously its otherwise eligible pages were indexable and self-canonical, creating
a second searchable copy of the website. There is no evidence that this caused a
particular Google position, but the verification mirror should not be a competing
search destination.

`Site` now identifies github.io deployment origins and renders `noindex,follow` on
every page, including Free Property Snapshots. Crawling remains allowed so search
engines can read the directive. The mirror does not advertise a sitemap and its
sitemap contains no URLs. The rendered-page audit reports both content eligibility
and actual indexing eligibility, and still checks crawlable paths on the mirror.

The auctiongeek.co.uk origin retains normal indexing rules, canonical URLs and its
sitemap. This behaviour depends on the actual deployment hostname; no global
noindex environment setting can accidentally be copied onto the main site.

Validation: 56 focused tests pass, including assertions for every mirror route,
snapshot robots directives, crawlability, empty mirror sitemap, correct main-domain
indexing, and the public Cloudflare export boundary. The subsequent CI run and live
mirror HTML must be checked before claiming this change deployed.

Google's [noindex documentation](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
confirms that crawlers must be able to access the page to read the directive.
This does not remove a page from Google's results immediately or guarantee rankings
for the main domain.
