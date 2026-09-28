# Auction Sniper integrated public platform

The collectors, publication gates and historical corpus remain authoritative.
The Python/FastAPI + Jinja frontend presents the established Auction Sniper board
as the website home, with the property, auctioneer, calendar and history pages
sharing its navigation and investment logic. Semantic HTML is rendered before delivery; search engines and
users do not need a Streamlit websocket or JavaScript to read public particulars.

## Run / publish

```
pip install -r web_platform/requirements.txt
uvicorn web_platform.app:create_app --factory
python -m web_platform.export --output public-dist --origin https://YOUR-DOMAIN
```

GitHub Pages publishes the **public static renderer only**. Old Streamlit board
bookmarks remain compatible; they are not a separate product destination. The
existing legal-pack workflow runs as a dedicated embedded view inside the site.
It does not run the private API. The same URLs/templates run dynamically through
ASGI when an account-capable host is connected. No account database or source
snapshots enter the public artifact. A publication workflow rebuilds after live
snapshot/corpus refreshes. This is an incremental release, not a DNS migration.

## Implemented boundary

- Useful home, paginated current properties, individual appearance URLs,
  auctioneer collections, dated auction pages/calendar, history, methodology and
  privacy and legal-pack research pages. No empty login, pricing or intelligence pages.
- The light property board keeps address search, auctioneer/price/yield/tenure
  filters, unknown-value handling, property-level target-yield calculations, guide ranges,
  current rent, investment details and research links. `investment_details.py`
  was extracted from the production-patched Streamlit code and is shared by both
  consumers; `property_summary.py` remains the shared opportunity-title logic.
  A small browser search index selects lazily loaded card bundles rendered by the
  same Jinja macro as the initial HTML. Filters have shareable URLs and browser
  history support. Public pages and pagination remain readable without JS.
- Stable source/date/lot identity; physical-property matching is separate.
  Exact-address history is labelled as candidate evidence, not verified UPRNs.
- Canonicals, XML sitemap, robots, semantic HTML, breadcrumbs/JSON-LD, accessible
  navigation, reserved image dimensions/lazy loading and responsive layout.
  Thin property records remain accessible but are noindex and excluded from the
  sitemap. No mass historical/city/category page generation.
- Private API verifies asymmetric managed-provider JWT signatures, issuer,
  audience, expiry and subject using PyJWT/JWKS. Unconfigured auth fails closed.
  Supabase Auth owns future registration/login/logout/reset and session refresh;
  we never store passwords. User roles never come from editable token metadata.
- Private saved-property endpoints are scoped to the verified account. SQLite
  account state is separate from public history, with owner-only file permissions.
  Use a persistent encrypted volume/backups on a single application instance;
  migrate this small account store to managed PostgreSQL before horizontal scale.
- Stripe-hosted recurring Checkout and billing portal adapters; configured price
  allowlist, authenticated customer binding, duplicate-subscription prevention,
  signed raw-body webhooks, transactional replay protection and fresh subscription
  retrieval for reordered events. Active/trialling status and expiry control
  server-side plan entitlements. Past-due/unpaid/cancelled accounts lose premium
  access; cancellation at period end retains access until that period ends.
  No success redirect or untrusted plan field grants access. API/business plans
  are represented without enabling an unpriced API product or granting admin.

## Activation deliberately not performed

Before offering accounts/payments: provision Supabase with asymmetric JWT keys,
verified redirect URLs, email verification, recovery, rate limits and production
email; build the authenticated dashboard with provider SDK session lifecycle;
connect a dynamic HTTPS host and persistent private database; configure a Stripe
account, products/prices, portal allowed changes and webhook destination; run
provider sandbox end-to-end tests for payment success, failure, cancellation and
recovery; publish the operator's contact, legal and account privacy information.
No credentials or paid promises are embedded in this public release.

Environment (server only): `PUBLIC_ORIGIN`, `AUTH_ISSUER` (Supabase /auth/v1),
`ACCOUNT_DATABASE_PATH` (outside repository), `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_INVESTOR`, `STRIPE_PRICE_PROFESSIONAL`,
`STRIPE_PRICE_BUSINESS`. Never commit `.env`, private DBs, tokens or card data.

Stripe is the initial adapter: hosted checkout, recurring billing and portal,
with no fixed software commitment for pay-as-you-go. UK public pricing checked
28 September 2026: standard UK cards 1.5% + 20p and Billing pay-as-you-go 0.7% of
Billing volume; international cards/other services differ. Recheck before launch.
Sources: https://stripe.com/gb/pricing and https://stripe.com/gb/billing/pricing,
https://docs.stripe.com/billing/subscriptions/webhooks,
https://docs.stripe.com/payments/checkout/build-subscriptions,
https://supabase.com/docs/guides/auth/jwts.

## Buyer fees and compact catalogue

The property search index includes captured addresses, tenants, tenancy schedules,
property types, descriptions and other descriptive particulars. All query words
must match, so `Admiral Liverpool` narrows a business search by location. Nearby
business mentions can also match; a keyword match does not prove that business is
the tenant. Search ignores case, accents and punctuation. The index stores unique
words to limit its size and excludes generated investment assessments and URLs.
The shipped JavaScript matcher is exercised with the Python index producer in
`tests/test_keyword_search.py` (requires Node, available on the CI runner).
Increment `SEARCH_INDEX_VERSION` if changing the index contract so a stale
address-only index cannot be served to the new search code.

Buyer-fee information lives in `auctioneer_fees.json`, independently of property
income, guide prices and GIY. Each profile records the official source, review
date, VAT wording, fee bands/minimums and scope. Regional lot examples are
labelled as examples and must never be promoted to house-wide tariffs without
evidence. BidX1 and Town & Country publish lot-specific fees; no universal
amount is invented. Profiles older than 90 days show a review reminder; new
auctioneers use an explicit unverified fallback. To refresh, read the current
official terms and each relevant exception, update the individual profile and
its date, run `pytest web_platform/tests`, then verify the published directory
and house page. The property-level estimator uses verified tariffs; it is not a total acquisition-cost calculator.

The directory supports name/region search and current-catalogue filtering. The
same evidence appears on each house page. Compact cards keep the four primary
metrics and yield target visible, with highlights, research links and detailed
facts in the existing disclosure. Card-template changes invalidate lazy-loaded
JSON bundle URLs; CSS and JavaScript carry a content version in their URLs.

## Still to build, intentionally outside this bounded release

Dashboard UI/provider integration, alerts, saved searches, account deletion and
retention controls, paid intelligence/report APIs, invoices surface (Stripe portal),
pricing decisions, custom domain and image optimisation/cache service.
Historical evidence and missing fields must remain truthful at every stage.

## Property review release — 28 September 2026

The main board keeps minimum/maximum guide, actual current-income GIY, tenure,
status and keyword filters. Target yield belongs only to property analysis; old
`target` query parameters are ignored without breaking other filters.

`particulars.py` groups captured source sentences and structured facts. It removes
exact repeated wording, preserves qualifications and numeric dates, retains the
source tenancy schedule and exposes the original captured text in a disclosure.
It does not generate invented summaries. Missing sections are omitted. Source
HTML section breaks are preferred where recovered.

`enrichment.py` supplements the published lot contract with exact-source ordered
galleries, source section text, logos and narrowly parsed lot fee clauses. It
never changes the hero, price, rent, status or commercial classification. HTML/API
responses are hashed and source/time references retained in `property_evidence.json`.
Failures preserve old evidence; repeated host failures stop further attempts in
that run. Writes are atomic. The daily/live-publication refresh checks at most 150
stale/new rows (seven-day cache) and commits only the evidence file. The public
renderer rebuilds after its successful completion. This is not historical lot
harvesting and is not counted as new appearances.

Fee calculations are explicit numeric bands in the verified fee registry, or
verified clauses bound to the exact lot URL. They use Decimal, known VAT treatment,
percentage minima and both ends of guide ranges. Unspecified boundaries, stale
profiles and unmatched lot-only examples remain unconfirmed. Savills' published
amount retains its unresolved VAT qualifier. A deposit is never added to a fee.
Calendar dates use UK wording; auctioneer logos have a text fallback where absent.
History remains in the corpus and at existing URLs, with guides, results, rents
and source links presented within each property. It is removed from main navigation.

`/plans/` distinguishes today's free tools from planned Premium/professional
services; no nonfunctional checkout or invented subscription price is advertised.
Existing Supabase/Stripe account and subscription boundaries remain intact.
The private service now also supports server-priced one-off orders for
`investment_report`, `legal_pack_report`, `featured_listing` and `data_export`.
Configure corresponding `STRIPE_PRICE_<UPPERCASE_PRODUCT>` variables only after
products can actually be delivered. Price IDs and customer identity are never
accepted from the browser. Signed checkout notifications trigger a current Stripe
session read, verify order/customer/price/quantity, and record payment idempotently.
Paid orders enter `paid_awaiting_fulfilment`; payment does not automatically publish
a sponsored listing or unlock a subscription. Refund/dispute notifications put
orders into review; late success notifications cannot restore them. Account APIs
expose only the signed-in user's order summary. There is no stored card data.

Before activation, provider sandbox end-to-end tests, authenticated dashboard,
production email, service fulfilment, pricing, operator terms/privacy, cancellation
and refund operations are still required. No account/payment API is deployed on
GitHub Pages. The public site clearly marks paid services as not yet open.
