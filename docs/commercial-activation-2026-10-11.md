# Commercial activation checkpoint — 11 October 2026

## Implemented, with public checkout closed

The existing Free / Investor / Professional identifiers are retained. The
Professional display name is Investor Pro. The shared catalogue defines £0,
£15 and £25 monthly prices, 0 / 1 / 3 included reports and £19 / £15 / £12
one-off or additional report prices. These are provisional launch assumptions.

Included credits are funded by verified paid monthly Stripe invoices. Each
period expires without rollover. Prorations do not create allowances; upgrading
does not reset usage. Current downgrades cap unused allowance, while previously
redeemed reports remain owned. Cancellation at period end retains access until
the paid period ends; immediate cancellation or failed payment stops new claims.
Claims and billing updates share a database transaction lock. A report can be
redeemed once, with concurrent purchases blocked. Completed redemptions and
one-off purchases survive subscription expiry; refunds/disputes require review.

Both report purchases and new credit claims respect the existing global quality
hold. Incomplete reports cannot expose the full paid projection or paid downloads.
Report retention/account-deletion terms must be agreed and published before opening.

Pricing cards and the scrollable comparison distinguish free browsing from
account features being activated and reports/email alerts coming soon. Restricted
workspace actions use contextual text and a pricing link. Existing free browsing,
homepage navigation and property search are preserved.

## Service changes verified before publication

- Supabase project `axoukcujpxkfvocwuaqg`: migration `report_credit_ledger`
  applied; all four new credit/payment/redemption/attempt tables have RLS.
  Browser roles have no private-schema access; security adviser has no findings.
  At inspection there were no registered users, private accounts or purchases.
- Stripe sandbox `acct_1UO22H2MK0UQoSLq`: existing monthly £15/£25 prices
  retained; product names updated. Test report prices:
  - £19: `price_1UPJLc2MK0UQoSLqnXFrLr2t`
  - £15: `price_1UPJMG2MK0UQoSLqnkuf4Eep`
  - £12: `price_1UPJMM2MK0UQoSLq1ZIUjUgT`
- Existing webhook `we_1UPA0A2MK0UQoSLqyoxP1Uun` now also subscribes to
  invoice paid, failed, voided and uncollectible events. Delivery is separate
  from endpoint configuration and remains to be proven with runtime credentials.
- Render's last failed build was evicted after exceeding the 16 GB temporary
  storage limit. A fresh release must be checked explicitly; this public-repository
  service's autoDeploy flag is not proof of Git-provider integration.

## Validation and evidence boundaries

Local account/provider suite: 129 passed, six disposable PostgreSQL checks
reserved for CI. Tests cover signed Stripe events and duplicate notifications,
concurrent credit consumption, renewal, cancellation, downgrade, refunds, account
isolation, return access and quality holds. Stripe API responses use the actual
SDK's recursive conversion; signed-event parsing is exercised with the pinned SDK.
The PostgreSQL workflow additionally restores a dump of disposable account/report
data using PostgreSQL 17 and verifies ownership. This is not a production backup
or recovery guarantee. Record its actual CI result and the deployed release below.

Every claimed generation attempt records elapsed/CPU time, bytes/files, document
coverage and available provider token/search usage, including failed attempts.
`GET /api/admin/report-usage` is owner-only. No provider means no measured AI cost.
`ACQUISITION_COST_RATES_JSON` must specify the exact model, effective date, input,
cached input and output USD/million-token rates, USD/search-call rate,
GBP/processing-second and GBP/document-page rates and USD-to-GBP conversion.
Missing or incomplete usage/rates produce unknown cost, never a fabricated zero.
Invoice reconciliation, payment fees and overhead are separate. At full credit
use, gross subscription revenue/report is £15 Investor and £25/3 Investor Pro;
this is not a measured margin.

## Activation still required

1. Configure an approved production email provider/sender in Supabase, verify
   delivery and real sign-in. Set `PRODUCTION_EMAIL_VERIFIED=true` only after
   that check. Bind `ADMIN_ACCOUNT_IDS` to the real verified owner identity.
2. Store the Stripe sandbox runtime key directly in Render as `STRIPE_SECRET_KEY`
   (never in source/chat), with permissions for the existing billing operations.
   Verify sandbox subscription, failed payment, refund and signed webhook delivery.
3. Confirm API release/readiness, exact website CORS/CSP connection and persistence
   on a fresh process before enabling public accounts. Keep `BILLING_LIVE=false`.
4. Configure the existing analysis provider with its secret and explicit model;
   run representative original packs, retain measured usage and approve analytical
   quality. Do not enable paid reports merely to demonstrate a checkout.
5. Agree retention/deletion terms and establish a production backup schedule and
   restore evidence. The isolated CI recovery drill does not cover Supabase Auth.
6. Complete the real desktop/mobile customer journey, including sign-out, return
   and download. Fixture tests are not that deployed customer acceptance test.

No live charging, report-quality approval, real provider costs or complete deployed
journey are claimed by this checkpoint.
