# Auction Geek activation checkpoint — 11 October 2026

The owner confirmed **Auction Geek** as the product name after the public
Cloudflare launch. Continue the existing account, payment and Acquisition
Intelligence implementations; do not restart them or resume historical expansion.

## Published implementation

Commit `a0165db6e35438d21377b9578f2d751c245ba75b` updates customer-facing
website, account, report and download branding, adds the AG favicon and homepage
WebSite metadata, and updates the backend's documented public origin. Existing
workspace storage keys, property identifiers, database records, service names and
Stripe product/price identifiers are preserved.

The selected website, Cloudflare packaging and report checks passed locally,
including real bundled SQLite fallback. GitHub's report tests, public publishing
checks and private PostgreSQL integration checks passed for that commit.

Cloudflare build `f4ad0f48-b4eb-4a4e-9cf5-30c2697dd74f` completed successfully.
Live HTTP and browser checks confirmed the new branding on the home, account,
pricing and Acquisition Intelligence pages, correct apex canonicals and the
exact committed favicon. Public accounts and billing remain disabled.

## Accounts

Supabase Auth now has `https://auctiongeek.co.uk/` as its Site URL and the exact
`https://auctiongeek.co.uk/account/` callback in its allow-list. The older GitHub
Pages callback remains available for compatibility. The saved values were
verified in the dashboard. No website users existed at this checkpoint.

Render's existing private API now has `PUBLIC_ORIGIN=https://auctiongeek.co.uk`.
The private PostgreSQL connection and existing access controls are retained.
Custom SMTP is still disabled, and public registration is not activated.

Deployment `dep-db5cta2d0e5s73f10dv0` reached live at 23:57:34 UTC on 10 October.
Both `/healthz` and `/api/readiness` returned 200, with CORS allowing exactly
`https://auctiongeek.co.uk`. Readiness reported accounts/database ready, owner
access not configured, analysis provider not configured and paid reports not
approved. The subsequent webhook-secret environment deployment
`dep-db5ctn3hu5js73do61h0` was still building at this checkpoint; the secret was
saved successfully, but actual webhook delivery has not been tested.

Next: configure the chosen email provider in Supabase Authentication > Emails,
verify sender-domain records, and test a real owner sign-in and confirmation
return. Use the verified identity endpoint to obtain the owner account ID for
`ADMIN_ACCOUNT_IDS`; never derive permission from an editable profile. Exercise
shortlist persistence across a restart, account isolation and every preview tier
before setting the public account configuration.

## Sandbox payments

The existing sandbox products now display **Auction Geek — Premium Investor**
and **Auction Geek — Professional**. Their existing monthly GBP prices remain
£15 and £25. Render has the corresponding existing price IDs configured.

Webhook `we_1UPA0A2MK0UQoSLqyoxP1Uun` points to the existing backend's
`/api/billing/webhook`, with API version `2026-09-30.endive`. It listens only for
the implemented Checkout completion/failure/expiry, subscription lifecycle,
refund and dispute events. Its signing secret was transferred directly into
Render's `STRIPE_WEBHOOK_SECRET`; it is not in code, chat output or this document.

The backend still needs a restricted runtime key from that same sandbox, saved
as `STRIPE_SECRET_KEY`. The integration needs Customer and Checkout-session
creation, Customer Portal sessions, and reads of subscriptions, Checkout
sessions, payment intents and charges. Keep the key restricted to the operations
used by this backend. `BILLING_LIVE=false` remains set.

Next: complete actual sandbox Checkout, verify webhook delivery and duplicate
handling, cancellation, failed renewal, refund/dispute blocking and account
ownership. A saved webhook is configuration evidence, not proof of successful
event processing or paid-launch acceptance.

## Acquisition Intelligence

The report and export branding is updated. The existing provider requires
server-only `OPENAI_API_KEY`, `ACQUISITION_PROVIDER=openai` and an explicit
`ACQUISITION_MODEL` in Render. No fresh paid provider run is claimed here.

Run the existing investigation against the original Newbury pack and the
materially different Wrexham, Maybrey and Dover cases once configured. Record
source coverage, visual disposition of unread pages, substantive review of each
document, external research, contradictory evidence, commercial usefulness,
actual cost and runtime. Preserve original/revised conditions separately.

Existing deterministic replay is only regression evidence: Newbury's identified
rents reconcile, while the other three cases remain unreconciled. It does not
satisfy independent investigation or owner acceptance. The paid-report quality
gate remains closed until the real reports meet the agreed standard.
