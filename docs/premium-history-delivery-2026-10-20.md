# Premium history delivery — 20 October 2026

## Commercial directive and order of delivery

Free discovery and useful deterministic snapshots remain public. Historical timelines, prior guides/results, income changes and historical comparables become premium. Configurable proposed prices: one property £2.99 permanently; site-wide history £5 for 24 hours; £10 for seven days later; Investor/Investor Pro membership includes history. £19 full reports remain separate and subject to their existing quality gate. £0 advertising and low infrastructure cost remain requirements.

1. Preserve catalogue, collection, snapshots and report development.
2. Remove historical detail from public output; serve it through verified account entitlements.
3. Verify Stripe checkout, webhooks, expiry, refunds and sign-in restoration before opening purchases.
4. Keep substantial crawlable public content and measure SEO rather than claiming rankings.
5. Continue source reconciliation, historic coverage and matching quality.
6. Connect owner analytics and demonstrate complete customer journeys.

## Implemented in this batch

- Public property HTML now contains only history existence/count previews, with visible £2.99/£5 choices marked coming soon. Complete historical prices, observations, comparables and source links are not embedded or CSS-hidden. The general history page is an explanatory public directory, not a raw historical-price feed.
- Authenticated `/api/history/{property_id}` checks current subscription or recorded purchase entitlement before rendering any private history. Responses inherit `no-store` and `noindex`. Customer metadata, query strings and checkout redirects do not grant access.
- Single-property entitlements use full address and tenure, not an auction appearance ID; this survives repeat appearances while keeping different tenures separate. Fuzzy matching is deliberately absent. Complex changes of extent/title still require acceptance work before sales.
- Day passes last exactly 86,400 seconds from the first verified fulfillment; webhook retries do not restart the clock. Supporter duration is 604,800 seconds but the product is disabled in the catalogue.
- Prices and durations live in `web_platform/plan_catalogue.json`. Stripe prices must match integer GBP amounts. Orders retain immutable price/duration/subject/terms and tax/receipt data.
- Checkout uses durable pending orders and Stripe idempotency, survives a lost response, blocks parallel overlapping history checkouts and already-owned access. Known expired checkouts can be replaced; unresolved old sessions fail closed.
- Existing signed webhook re-reads Stripe Checkout/PaymentIntent/charge and verifies customer, account, session, price, quantity, amount, currency and environment. Unpaid or failed notifications grant nothing. Refund/dispute statuses revoke history through the original purchase record, and late success cannot restore it.
- Duplicate appearances are removed from timelines; address token boundaries distinguish 1–3, 13 and 1/3. Material recorded area differences and missing tenure are identified. This is not certification of every historical match.
- Existing source archive and scheduled collectors are untouched. Free snapshots still use their existing deterministic data projection and browser print path, with no history loading, AI provider or paid PDF API.
- Private production table `auction_private.history_order_terms` installed with RLS and backend-only access. Verified `anon` and `authenticated` cannot SELECT it; `auction_api` can use it.
- Sandbox Stripe products created: `auction_geek_property_history` / `price_1USkIv2MK0UQoSLq3Deg3A5F`; `auction_geek_history_day_pass` / `price_1USkJP2MK0UQoSLqmiofR27f`. Render receives these non-secret IDs through an additive merge. No live prices or real customer charges created.

## Security blocker discovered: the archive is already public

GitHub repository `garethburke5/Commercial-Auction-Sniper` is public. It contains historical source/appearance files, database parts, and prior commits. Consequently removing website HTML does **not** make the archive private. Existing public copies and third-party caches cannot be retrospectively guaranteed secret.

Before history sales:

- Inventory all public download paths: repository blobs/history/releases/artifacts, GitHub Pages, Cloudflare deployment previews, the legacy Streamlit app, current-catalogue archives and any historical exports.
- Select and verify a private archive location or repository with the existing hosting/build/collector connections. Keep a checksummed backup and compare corpus counts. Do not remove the only retained evidence or blindly change repository visibility and break deployment.
- Change collectors to write privately; give builders/readers least-privilege access; publish only public projections. Stop public archive replication and verify old public URLs cease serving files where controllable.
- Reconcile title/extent and source confidence on the paid acceptance set. Do not assume exact-address matching proves like-for-like property ownership.

`HISTORY_ARCHIVE_PRIVATE=false`, `HISTORY_QUALITY_APPROVED=false`, and `HISTORY_SALES_ENABLED=false` remain set. All three are required for customer checkout. An owner-only sandbox endpoint can exercise the journey using test keys while live billing is disabled.

## Payment and tax acceptance still open

The local payment tests use Stripe doubles and real HMAC signature checking; they are not successful Stripe test transactions. Sandbox products and configured price IDs are not fulfillment acceptance. Demonstrate hosted checkout success, decline/async failure, verified webhook arrival, access without return redirect, logout/reopen, day-pass expiry, refund/dispute, duplicate tabs and immutable receipt/accounting records using real Stripe sandbox sessions.

VAT registration/treatment is not established by this change. Customer checkout additionally requires an explicitly confirmed tax mode: `not_registered`, or `inclusive_manual` with a verified active inclusive Stripe tax rate in the matching environment. No automatic Tax service, guessed registration or tax-code selection is enabled. Refund/access terms and applicable consumer cancellation handling must be reviewed and presented before sales; the stored terms version alone is not customer consent.

## SEO and analytics status

Current property content, free snapshots, titles/descriptions, canonicals, internal listing/auctioneer/calendar links, robots and sitemap eligibility remain. Property WebPage JSON-LD marks the premium section with `isAccessibleForFree` and `hasPart`; bots receive the same public preview as visitors. No crawler bypass exposes premium data.

Still outstanding: wider historical auction/geographic pages with genuinely useful public research; old-static-slug redirect verification; actual Search Console/Bing verification and indexing reports; mobile Core Web Vitals measurement; connected Cloudflare visitor metrics; snapshot conversion instrumentation; product revenue and checkout-error dashboard. Backlink totals are unavailable until a provider is connected and must be labelled accordingly. No advertising, backlink purchase or extra analytics subscription was introduced.

## Existing launch work remains required

The £19 report acceptance programme is not replaced by this history work: original-pack interpretation, proportionate commercial analysis, natural writing, end references, unfamiliar-property holdouts, customer delivery/refunds and measured costs remain open. Scheduled current collection and the bounded six-hour historical continuation remain configured; this does not establish all-UK or 20-year completeness. See the master backlog for report, archive, account, email and launch priorities.
