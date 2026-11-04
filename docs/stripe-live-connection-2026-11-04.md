# Stripe live connection — 4 November 2026

## Completed and verified

The owner completed renewed Stripe authorisation. Live AuctionMash account
`acct_1UO227RpkJti4bUn` now supports reads and writes. Five products and seven
prices were created, then read back: all active, GBP, live mode, tax-inclusive
price behaviour. This does not set a VAT rate or enable paid Stripe Tax.

| Render variable | Live Stripe price |
| --- | --- |
| STRIPE_PRICE_INVESTOR | price_1UY2r4RpkJti4bUnTrZsTywn |
| STRIPE_PRICE_PROFESSIONAL | price_1UY2rYRpkJti4bUnH2qVC8vI |
| STRIPE_PRICE_LEGAL_PACK_REPORT | price_1UY2roRpkJti4bUnrMWa7a8h |
| STRIPE_PRICE_REPORT_INVESTOR | price_1UY2s7RpkJti4bUn5rg4Imdw |
| STRIPE_PRICE_REPORT_PROFESSIONAL | price_1UY2sQRpkJti4bUn5LPKtpeV |
| STRIPE_PRICE_PROPERTY_HISTORY | price_1UY2sgRpkJti4bUnhBqFzYbZ |
| STRIPE_PRICE_HISTORY_DAY_PASS | price_1UY2suRpkJti4bUnEtDBVaV2 |

- Investor: £15/month, one report credit; Investor Pro: £25/month, three credits.
- Standard report: £19; additional member reports: £15 Investor / £12 Pro.
- Property history: £2.99 once; history day pass: £5 once, 24 hours.
- Created live webhook `we_1UY2utRpkJti4bUnOrJZSdJr` for
  `https://auction-sniper-private-api.onrender.com/api/billing/webhook`.
- Subscribed to the 14 checkout, subscription, invoice, refund and dispute
  event types handled by Billing.webhook. No wildcard event subscription.
- Saved seven price IDs and the signing secret directly to the existing Render
  service with merge semantics. No secret values are stored in this repository.
- BILLING_LIVE remains false. No customer charge or live transaction was made.

## Deployment and remaining activation work

Render accepted the configuration, but deploy `dep-dblhug3ncjis73dtl6rg`
failed immediately with `pipeline_minutes_exhausted`. The changed environment
is saved, not verified active. Before the update, production readiness served
release `8217a81105618a4d2355cbf9a3d932b7d0171503`, with paid_reports_approved
true but live_billing_configured and all checkout flags false.

The website still needs a live Stripe runtime key stored securely as
STRIPE_SECRET_KEY; ChatGPT OAuth access does not supply an application key.
Confirm VAT rate/registration treatment, configure the inclusive manual rate,
complete the customer portal, reconcile sandbox customer/entitlement records,
and test signed fulfilment and account access before opening checkout.
The historical archive/privacy requirements in the earlier launch log remain.
Webhook creation and price verification are not proof of payment fulfilment.

This checkpoint supersedes the earlier connection-blocked and empty-catalogue
statements in commercial-launch-2026-10-31.md. It does not claim payments live.
