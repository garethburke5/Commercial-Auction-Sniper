# Organic launch checkpoint — 17 October 2026

The £0 paid-advertising requirement is recorded in the existing launch roadmap. This is a focused technical acceptance check, not a new content or promotion workstream.

## Independently checked on the public website

- Homepage, pricing, account shell, a property, an auctioneer, an auction page and catalogue page two returned HTTP 200. A deliberately missing URL returned a genuine 404 with noindex.
- The sitemap returned 1,584 unique URLs, all on `auctiongeek.co.uk`: 1,440 property pages, 69 auction URLs, 47 auctioneer URLs, 21 catalogue URLs and seven other pages. These are sitemap entries, not evidence of search-engine indexing or visitor numbers.
- Sampled pages have canonical URLs, titles and descriptions. Their existing WebPage/BreadcrumbList JSON-LD parses successfully. The homepage also identifies the website. No rich-result eligibility or rankings are inferred.
- A www request redirected with HTTP 301 to the root hostname, preserving the page path and query string; the destination canonical omitted the tracking query.
- The public account shell has noindex and is excluded from the sitemap. Private account/report content remains protected by API authentication.

## Focused corrections

Commit `1053ec716a83dd527a4794c7ffc697c8d7db26c9` gives paginated catalogue pages distinct page-number titles/descriptions while retaining their self-canonical URLs. Static export and ASGI now share the robots policy. The public sign-in shell is crawlable so its existing noindex tag can be read; private API routes remain disallowed and authenticated.

21 focused platform/export tests passed locally; two SQLite-environment-specific tests were excluded from that local run. Hosted validation for the SEO release passed 329 platform tests (12 skipped), 69 PostgreSQL tests and the browser workflow. Render deployed `1053ec716a83dd527a4794c7ffc697c8d7db26c9` successfully at 20:29 UTC; an independent readiness request returned that exact release with live billing and paid-report approval disabled.

Independent post-deploy requests returned HTTP 200 for `/properties/page/2/`, with the title `Auction properties — Page 2 | Auction Geek`, and `/account/`, with `noindex,follow`. The live robots file allows crawling of the public shell while disallowing `/api/`. These checks establish deployed changes, not search-engine indexing.

## Still outstanding

- Verified ownership/access and sitemap submission in Google Search Console and Bing Webmaster Tools; actual indexing, impressions, clicks, query positions and visitor/referral evidence.
- Measured mobile performance/Core Web Vitals and broader sampling of original property/history value. A small HTTP sample is not a whole-site quality audit.
- Address-slug changes must preserve existing public URL equity. The ASGI route has an ID-based redirect; equivalent behaviour for old slugs on the static Cloudflare deployment is not yet verified.
- Useful location pages and additional free resources remain after essential launch work; do not mass-publish thin combinations. The scoped commercial buyer checklist is still deferred.
- AI discovery should build on readable, sourced, dated public information and normal crawl/index quality. No private reports are exposed and no special AI visibility outcome is promised.

Official guidance consulted: https://developers.google.com/search/docs/crawling-indexing/block-indexing ; https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap ; https://developers.google.com/search/docs/appearance/ai-features


## Owner traffic and SEO reporting — requested 17 October 2026

Add site statistics to existing launch priorities 8/9 and the £0 organic acquisition requirement. Reuse free provider dashboards first; do not build a new analytics service or buy an SEO subscription. Owner access should link to the verified dashboards initially. A consolidated owner-only summary can follow once access and data are proven; missing data must be labelled unavailable, not zero.

| View | Metrics | Initial free source |
| --- | --- | --- |
| Audience and content | Visits, page views, popular pages, referring sites, countries, desktop/mobile, page performance | Cloudflare Web Analytics |
| Google discovery | Impressions, search clicks, click-through rate, average search position, queries, landing pages, indexing/sitemaps | Google Search Console |
| Bing discovery | Search impressions/clicks, queries, indexed/crawled URLs and site issues | Bing Webmaster Tools |
| Links | Discovered inbound links, referring domains, linked pages and internal-link information where supplied | Google Links report and Bing Backlinks |
| Commercial outcomes | Aggregate verified registrations, subscriptions and completed report purchases | Existing private account/Stripe records after launch acceptance |

Definitions matter: Cloudflare visits are navigation/referral-based visits, not a guaranteed deduplicated count of people. Hosting request totals include bots and assets and must not be labelled visitors. Use available bot exclusions and identify internal testing. Search impressions are appearances in search results, not site visits. Backlink datasets are provider-discovered samples, may lag, and must not be added together as a unique total. Rankings and traffic are not guaranteed.

Inspection on 17 October: repository search found no analytics integration; the checked public homepage HTML response contained no known Cloudflare/Google/Clarity/Plausible tracking script and no Google/Bing verification meta tag. This does not prove that Cloudflare edge analytics are absent or that DNS-based webmaster verification is missing. No private provider dashboard or historical traffic count has been verified. Nothing was enabled by this inspection.

Activation acceptance:
1. Inspect existing Cloudflare Web Analytics hostname settings and verify collection for the intended UK audience; do not assume automatic injection works everywhere. Avoid duplicate beacons.
2. Verify owner access to Google/Bing, submit the existing canonical sitemap and check returned reporting data.
3. Keep analytics out of private account/authentication/report flows, exclude sensitive URLs and never send emails, tokens, document text or property notes. Check the actual beacon payload and update the privacy text to match the enabled implementation.
4. Verify a controlled public visit, source/page/device attribution and delivery of metrics; record the start date and reporting delays. Show 7-/28-day trends only once data exists.
5. Keep dashboard/API credentials server-side. Any eventual owner summary must use the existing server-verified owner permission; hiding a navigation item alone is insufficient.
6. Use existing provider exports/APIs where supported. Do not promise automatic Google backlink ingestion: the Links report export and the Search Console performance API are different capabilities.

This is scoped and pending activation, not a claim that analytics or an owner statistics page is live. Existing launch fixes retain priority.

Official references checked:
- https://developers.cloudflare.com/web-analytics/about/
- https://developers.cloudflare.com/web-analytics/get-started/
- https://developers.cloudflare.com/web-analytics/data-metrics/high-level-metrics/
- https://developers.cloudflare.com/web-analytics/data-metrics/dimensions/
- https://support.google.com/webmasters/answer/10268906
- https://support.google.com/webmasters/answer/9049606
- https://www.bing.com/webmasters/help/backlinks-c3a334e8
