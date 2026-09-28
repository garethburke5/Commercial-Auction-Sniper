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
  filters, unknown-value handling, target-yield calculations, guide ranges,
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

## Still to build, intentionally outside this bounded release

Dashboard UI/provider integration, alerts, saved searches, account deletion and
retention controls, paid intelligence/report APIs, invoices surface (Stripe portal),
pricing decisions, custom domain and image optimisation/cache service.
Historical evidence and missing fields must remain truthful at every stage.
