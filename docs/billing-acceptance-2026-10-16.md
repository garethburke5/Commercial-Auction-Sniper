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
