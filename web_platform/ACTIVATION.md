# Private-service activation — current boundary

The public Pages deployment is operational without account/payment secrets.
Registered Save is free; Watch, saved searches and alerts require membership.
Earlier device records remain readable/exportable. This is not an activated
cloud account service: registration and checkout explain their activation boundary.

## Required operator inputs

1. A Supabase project URL and publishable/anon key (public configuration), and its
   asymmetric Auth issuer (`https://PROJECT.supabase.co/auth/v1`). Enable verified
   email, magic-link PKCE sign-in, production SMTP, rate limits, and the exact
   `/account/` redirect on the chosen public domain. No password is stored here.
2. An HTTPS ASGI host with persistent encrypted storage and backups. Set
   `ACCOUNT_DATABASE_PATH` outside the repository. Run the existing
   `uvicorn web_platform.app:create_app --factory`. Use one application instance
   with SQLite; move private state to managed PostgreSQL before horizontal scale.
3. `PRIVATE_API_ORIGIN`, `PUBLIC_ORIGIN`, `SUPABASE_URL`,
   `SUPABASE_PUBLISHABLE_KEY`, `AUTH_ISSUER` in the deploy environment. Pages uses
   the public values at export. Secrets never enter its output.
4. Stripe test keys, webhook signing secret, configured Price IDs
   `STRIPE_PRICE_INVESTOR`, `STRIPE_PRICE_PROFESSIONAL`,
   `STRIPE_PRICE_LEGAL_PACK_REPORT`, and (when sold) `STRIPE_PRICE_FEATURED_LISTING`.
   Prices stay provider-configurable. The recurring billing portal must allow the
   intended plan changes/cancellation. Webhook endpoint: `/api/billing/webhook`.
5. Set `ADMIN_ACCOUNT_IDS` to the server-derived SHA-256 identity of the owner's
   verified Supabase issuer/subject. Never use editable user metadata as admin.
6. Optional `COMPANIES_HOUSE_API_KEY` for current official company evidence.
7. Operator/business identity, support contact, refund/cancellation terms and
   account/document retention policy. Confirm report fulfilment and actual cost
   before setting `BILLING_LIVE=true` in the public export.

## Customer journeys implemented

- Provider magic-link registration/sign-in/sign-out; owner-scoped saves, watches,
  notes, bid targets, saved searches and report index. Device data is not silently
  uploaded or copied to account storage.
- Save = shortlist; Watch = guide/status/date/legal-pack/detail observations and
  a change log. Changes are checked on return; scheduled email delivery is not
  claimed or activated. Digest preferences are stored for subsequent delivery.
- Account report upload → complete pack processing → private persisted report →
  server-projected free snapshot → Stripe one-off order bound to that report →
  signed webhook → full owner-only report/download. Redirects cannot unlock it.
  Purchases/refunds/disputes remain subject to existing server-side checks.
- Owner listing form → validated draft/live state with optimistic concurrency,
  promotional expiry, public deals API, enquiry inbox and first-party counters.
  Payment never bypasses publication validation or constitutes endorsement.

## Launch checks still requiring live provider configuration

Email delivery/verification/recovery, cross-account isolation, failed and expired
checkout, webhook retries/reordering, cancellation, refund/dispute lockout,
full-report revisit/download, listing/enquiry ownership, backups and restoration.
Use Stripe sandbox first; do not charge a real customer to test activation.
Subscription report credits are **not allocated** until a costed allowance is
chosen. One-off report access is currently the complete-delivery route.

## Course correction — 5 October 2026

The public offer is configured in `plan_catalogue.json`: Free £0, Premium
Investor £15/month and Professional & Business £25/month. Before enabling
checkout, configure the corresponding Stripe monthly GBP prices and match their
Price IDs to this catalogue. Do not claim an activated subscription while the
private host, identity provider or checkout remain unavailable.

Save requires a registered account and remains free. Watch, saved searches,
alerts, private note editing and saved bid targets require active membership.
Server entitlement checks cover direct workspace writes and saved searches;
expired subscriptions stop generating watch events. Previous customer records
are preserved, and users can still stop a watch or clear their data. Earlier
device backups remain readable/exportable, but cannot activate membership.

Full Acquisition Reviews remain separately purchasable by free accounts, bound
to the owner and exact report. No included review allowance or member discount
is promised until costs and fulfilment are established. The ordinary property
yield calculator remains free. Professional exports mean research exports, not
a restriction on downloading a customer's own stored data.

## Owner setup confirmed missing — 7 October 2026

The owner confirmed that Stripe, Supabase and a private API host do not yet exist.
This is an account-creation boundary, not a missing secret that can be recovered.

1. Create the owner-controlled Supabase project and Stripe sandbox. The owner must
   complete Stripe business verification before live payment activation.
2. Configure production SMTP for Supabase magic links, with a verified sender
   domain and `https://garethburke5.github.io/Commercial-Auction-Sniper/account/`
   as the redirect. Supabase's default mail service is not for public sign-ups.
3. Deployment is prepared as `web_platform/Dockerfile`, including PDF/OCR tools,
   a single Uvicorn worker, and `/healthz`. `web_platform/render.example.yaml`
   is an optional Render blueprint (2 GB compute, 5 GB persistent disk). It is
   inert until imported; review the provider's displayed recurring cost first.
   The container needs its mounted `/var/data` directory. Never deploy SQLite on
   an ephemeral filesystem or increase the instance count. A real container build
   and persistence/restart test still require the host; no Docker daemon was
   available in the implementation workspace.
4. Enter provider secrets directly in host settings. Set the four public Pages
   variables described above, keeping `BILLING_LIVE=false` during sandbox tests.
   Bind the two monthly plans and one-off report to their configured Stripe prices.
5. Verify customer registration/email return, account isolation, Save, paid Watch,
   failed/expired checkout, signed webhook retries, cancellation/refund and
   purchased-report revisit/download. Confirm report quality, customer terms,
   support contact, retention and database backup/restore before live billing.

### Watch worker

`python -m web_platform.monitoring` records watch events without a browser visit.
Run it on the private host every 15 minutes with the same persistent
`ACCOUNT_DATABASE_PATH` and refreshed canonical snapshot as the API. It stops
on data older than 14 hours, withholds degraded-source observations, checks paid
entitlement, preserves missing-property baselines and deduplicates retries.
Do not copy private data into public CI. The command is tested, but no host
schedule exists yet. With Render, a separate cron/worker cannot mount the web
service's disk: run scheduling in the same service, or move state to managed
PostgreSQL before separating workers. Email and saved-search match delivery
remain unimplemented and must not be sold as operational.

Provider references checked 7 October 2026:
- https://supabase.com/docs/guides/auth/auth-smtp
- https://docs.stripe.com/get-started/account/set-up
- https://render.com/docs/disks
- https://render.com/docs/blueprint-spec
