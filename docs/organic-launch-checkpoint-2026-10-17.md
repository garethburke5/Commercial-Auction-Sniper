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

21 focused platform/export tests passed locally; two SQLite-environment-specific tests were excluded from that local run. Hosted checks install the required dependencies. Deployment completion and independent post-deploy requests must still be recorded.

## Still outstanding

- Verified ownership/access and sitemap submission in Google Search Console and Bing Webmaster Tools; actual indexing, impressions, clicks, query positions and visitor/referral evidence.
- Measured mobile performance/Core Web Vitals and broader sampling of original property/history value. A small HTTP sample is not a whole-site quality audit.
- Address-slug changes must preserve existing public URL equity. The ASGI route has an ID-based redirect; equivalent behaviour for old slugs on the static Cloudflare deployment is not yet verified.
- Useful location pages and additional free resources remain after essential launch work; do not mass-publish thin combinations. The scoped commercial buyer checklist is still deferred.
- AI discovery should build on readable, sourced, dated public information and normal crawl/index quality. No private reports are exposed and no special AI visibility outcome is promised.

Official guidance consulted: https://developers.google.com/search/docs/crawling-indexing/block-indexing ; https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap ; https://developers.google.com/search/docs/appearance/ai-features
