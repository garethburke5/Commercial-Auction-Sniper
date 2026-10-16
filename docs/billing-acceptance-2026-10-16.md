# Auction Geek billing acceptance — 16 October 2026

## Deployed sandbox evidence

Isolated QA subscription: sub_1UR76C2MK0UQoSLqTaLdvWkN. The proprietor's
membership was not changed. Stripe was advanced in the user's browser; the
deployed PostgreSQL records were independently read after signed webhook delivery.
No report-credit rows were manually seeded.

| Check | Observed result |
| --- | --- |
| Initial Pro payment | £25 paid; professional allowance 3, 15 Oct–15 Nov. |
| Pro renewal | £25 paid; a separate allowance 3, 15 Nov–15 Dec. |
| Duplicate delivery | Two resent events returned HTTP 200; no duplicate period or increased allowance. |
| Scheduled downgrade | Investor £15 invoice paid on 15 Dec; backend active/investor; allowance 1, 15 Dec–15 Jan. |
| Scheduled cancellation | Active through the paid period; Stripe canceled on 15 Jan 2027; backend status canceled after clock advancement to 16 Jan. |
| No further renewal | Invoice list remained at three paid invoices; no January credit period created. |

Invoices: in_1UR76C2MK0UQoSLqcfnCeZfj,
in_1UR7eR2MK0UQoSLqttJeOXIR, in_1UR8G22MK0UQoSLqBdVJfnHe.

The Stripe clock is ahead of the application's real wall clock. These checks prove
webhook lifecycle persistence and period allowances; they do not independently
prove current API balances or redemption expiry at simulated dates. No-rollover
and access enforcement still require clock-controlled application checks.
Failed renewal/recovery and the complete generated-report customer journey remain
outstanding. Live billing and paid-report quality approval remain closed.

## Backend reliability finding and change

Render was still on the free compute plan. At 09:45 UTC it started the process;
the app then spent 43.90 seconds loading the catalogue and reached API readiness
after 45.40 seconds. Stripe deliveries subsequently processed successfully at
09:46:09 and 09:46:10, despite earlier timeout reports in Stripe.

Private API startup now defers construction of the existing Site/Catalogue until
a property-dependent request needs it. Public rendering is unchanged. A lock
prevents duplicate initialization, failed loads can retry, and shutdown does not
initialize unused data. Synchronous Stripe/database webhook processing runs in
a worker thread; HTTP acknowledgement still waits for the durable result.

Tests cover lazy loading, concurrent initialization, recovery after failure,
unused shutdown, webhook body limits, error propagation, and health/billing
responsiveness during blocked webhook/property work. Hosted CI and deployment
measurements must be checked separately; local tests alone are not deployment
acceptance. This change does not remove Render's free-plan idle spin-down.

## Verified backend deployment

Commit `1175fa3692b705d4fb526564a76c13668ef08d8b` went live on Render
at 11:06:59 UTC (deployment `dep-db907k6q1p3s739k1b0g`). Application
initialization was 1.70 seconds. Health and readiness returned HTTP 200;
unauthenticated account/identity requests returned 401 and an unsigned webhook
returned 400. Hosted CI passed 259 tests with 6 skips and 19 PostgreSQL checks.
Free-instance wake-up latency and reliable automatic deployment remain separate
operational issues. Live billing and paid-report approval stayed disabled.

## Failed-payment recovery correction

The account API now returns customer-scoped billing status without exposing
Stripe customer or subscription identifiers. A failed payment has an explicit
explanation, a payment-management action where available, and a support contact
when public billing is closed. Existing owner-only sandbox controls are reused.
Accounts without a Stripe customer no longer show an unusable billing button.
Returning from the existing Stripe portal verifies membership against the API;
a return URL alone cannot confirm payment. Cancellation is distinguished from
a pending update. Notices clear on sign-out and customer changes.

Local verification: 25 report-credit tests, 22 platform/membership/account tests,
and 32 client navigation tests passed. Signed failed-renewal and recovery
regressions cover Investor and Investor Pro, a new monthly allowance without
rollover, retained earlier paid reports, customer isolation, and duplicate/late
webhook notifications without duplicate credit grants. These tests mock Stripe
responses and control application time; they are not actual Stripe sandbox
transactions.

The connected Stripe tool exposes only a live-mode account. The sandbox browser
requires sign-in. Actual sandbox failed-renewal/recovery remains BLOCKED pending
that access. No live payment or proprietor subscription was changed. 
## Recovery correction deployed

Commit `62012b58c724d0be8e99f3c57ff35a8d549f05bb` passed hosted application
CI (263 passed, 6 skipped) and PostgreSQL CI (19 passed). Cloudflare Workers
Builds and public publishing both reported success for this commit. Render
deployment `dep-db963ll9fdbs7393l39g` went live at 17:47:59 UTC; application
initialization was 1.56 seconds and subsequent health checks repeatedly returned
HTTP 200.

This verifies the release and controlled regressions, not an authenticated
customer payment-recovery journey. The browser connection timed out while
preparing secure sandbox sign-in and then failed to return its recovery guidance.
No credential request or payment operation was submitted. A fresh deployment
screenshot could not be captured. Sandbox recovery remains outstanding.


The public readiness endpoint independently returned HTTP 200 with release
`62012b58c724d0be8e99f3c57ff35a8d549f05bb`: accounts ready, billing configured,
owner access configured, live billing disabled, paid reports unapproved, analysis
provider unconfigured, and production-email verification flag unset. That last
flag alone does not prove that previously tested account email is undeliverable.
