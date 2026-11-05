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

The owner reported saving a live Stripe runtime key as STRIPE_SECRET_KEY on
4 November. Its deployment failed with pipeline_minutes_exhausted; runtime use
of the new key has not been verified. ChatGPT OAuth access does not supply an
application key. Complete the location-aware tax/pricing work below, the customer
portal, sandbox customer/entitlement reconciliation, and signed fulfilment and
account-access checks before opening checkout.
The historical archive/privacy requirements in the earlier launch log remain.
Webhook creation and price verification are not proof of payment fulfilment.

This checkpoint supersedes the earlier connection-blocked and empty-catalogue
statements in commercial-launch-2026-10-31.md. It does not claim payments live.

## Owner-confirmed billing decision — 5 November 2026

- Legal business: Burke Commercial Ltd.
- VAT registration supplied by the owner: GB528469357. Recording this does not
  claim independent HMRC validation or that Stripe's legal-entity details have
  been updated.
- UK Full Investment Report purchases: £19 total, inclusive of applicable UK VAT.
- Overseas Full Investment Report purchases: £19 base price, exclusive of any
  applicable tax. Do not restrict paid checkout to UK customers as a substitute
  for implementing this policy.
- Do not automatically apply UK VAT to all overseas customers, assume all
  overseas purchases are exempt, or add 20% universally. Customer location,
  business/customer status, product treatment and relevant registrations must
  determine any tax added. The user has not approved paid Stripe Tax or any
  other new paid service.
- The existing seven Stripe price objects were created as inclusive. They do
  not implement the overseas exclusive-price rule. Preserve current UK prices;
  implement the overseas price treatment separately. This decision explicitly
  concerns the £19 report; do not silently change other product prices.
- Current billing.py applies one configured manual rate to all checkouts without
  customer-location selection. That is not a completed implementation of this
  policy. No tax-rate, environment or checkout activation change was made by
  recording this decision.

Required verification before marking the policy implemented: UK report total
stays £19 with the correct tax breakdown; an overseas sale keeps a £19 net base
and adds only the tax applicable to that transaction; changes to customer
location cannot reuse an incorrectly priced session; invoices, refunds and
server-side fulfilment preserve the agreed amounts and tax treatment.

## Verified progress — 5 November, 00:18 UTC

- Created and read back overseas standard-report price
  `price_1UYELbRpkJti4bUnlrnQIlHr`: active, live, GBP 1900 minor units,
  tax_behavior=exclusive, lookup_key=auctiongeek_report_overseas_gbp.
  Existing UK inclusive price is unchanged. The new price is not yet routed
  into website checkout; tax calculation and location selection remain pending.
- Created and read back default live customer portal configuration
  `bpc_1UYELyRpkJti4bUnEXhY9OnW`: invoices, payment-method updates,
  name/email updates and cancellation at paid-period end enabled. Plan switching
  remains off. Return URL is https://auctiongeek.co.uk/account/.
- Explicitly selected Render Environment > Edit > Save and deploy in the
  dashboard. Deploy `dep-dblskvbm8hqs73a3e2h0` still failed, with
  pipeline_minutes_exhausted at 00:14:53 UTC. No spend limit or plan changed.
  This disproves the proposed no-rebuild route for this attempt; do not claim
  the saved key is active or that a free workaround has been verified.
- Live readiness still reports release 8217a81105618a4d2355cbf9a3d932b7d0171503,
  accounts_ready=true, paid_reports_approved=true and all checkout flags=false.
- Stripe connector supports product prices and customer portal setup but does
  not expose manual tax-rate or account-tax-ID operations in this session.
  Dashboard fallback currently requires Stripe sign-in. No paid Stripe Tax,
  customer charge, tax registration or runtime activation was performed.
