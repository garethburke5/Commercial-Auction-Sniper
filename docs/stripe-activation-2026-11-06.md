# Payment activation checkpoint — 6 November 2026

## Verified today

- The existing Stripe connector identifies AuctionMash live account
  `acct_1UO227RpkJti4bUn`. Dashboard sign-in is separate and was not completed.
- Stop sending the owner through the cloud-browser email verification flow.
  Stripe requires the verification link in the originating browser; the owner
  has repeatedly reported that the proposed handoff does not work for them.
- Render deploy `dep-dbmrdnou01pc739ejkv0` failed at 11:15 UTC with event
  `pipeline_minutes_exhausted`. The spend cap was not changed. Do not retry
  Save and deploy as a purported free fix: the previous checkpoint records
  that route failing too.
- Current billing code still applies one fixed manual tax rate to all buyers.
  The overseas exclusive Stripe price exists but is not routed into checkout.

- Updated the existing live Stripe customer portal to link to Auction Geek's
  verified public privacy page. Invoice access, payment-method updates and
  cancellation at paid-period end remain enabled. No price or subscription
  was changed.

## Implemented in this change

`scripts/stripe_live_setup.py` uses the application's existing environment key.
It defaults to a read-only preflight. It checks the connected account ID and
legal company name, eight live prices (amount, currency, product, interval and
tax behaviour), webhook destination/events, and default customer portal.
It reports charges/payouts enabled separately; a matching configuration is not
proof of live payment delivery.

With `--apply-uk-vat` it creates only missing UK 20% inclusive/exclusive manual
VAT rates, after completing those checks. It paginates existing rates, reuses
matching ones, uses stable idempotency keys and reads back new objects. Partial
failures can be retried without replacing a previously created matching rate.
It does not switch checkout on, modify prices, configure paid Stripe Tax, add
tax registrations, update the account identity, or decide overseas tax liability.
The exclusive UK rate is preparation only: it is not an instruction to apply
UK VAT to every overseas sale.

Run in a trusted environment where the already-authorised live key is securely
provided as STRIPE_SECRET_KEY; do not put the key in a command argument, chat,
repository or log:

```sh
python scripts/stripe_live_setup.py
python scripts/stripe_live_setup.py --apply-uk-vat
```

The command has **not** been executed against live Stripe. The connector does
not expose the manual tax-rate operations, and the application key saved in
Render is not available to this execution environment. Do not describe rates
as created until a real execution and read-back succeeds.

Customer-facing standard-report terms are shared across pricing, property and
report-intake pages: £19 including VAT for UK customers; £19 plus applicable
tax overseas. Existing price amounts, member discounts, access controls and
checkout availability remain unchanged.

## Validation

27 automated checks passed, including an actual Stripe 15.6.1 SDK transport
test using synthetic HTTP responses and pagination. Tests cover mismatched
accounts/legal entities, wrong prices/tax behaviour, incomplete webhook setup,
portal cancellation behaviour, duplicate prevention, partial failures and
redacted error output. No customer payment or live tax mutation was made.

## Remaining before payment activation

1. Execute the setup command with the existing live server credential and
   confirm the company VAT number appears on invoices. The owner supplied
   GB528469357; independent HMRC validation is not claimed.
2. Resolve the report's tax treatment for overseas customers, then implement
   and verify location-aware checkout. Country alone does not establish all
   tax obligations. Do not assume overseas means exempt or restrict the site
   to UK purchases in place of this work. No paid tax service is approved.
3. Restore deployment capacity or agree a concrete alternative; the existing
   Render service cannot apply pending configuration with exhausted minutes.
4. Reconcile sandbox customer/entitlement records and verify real checkout,
   signed webhook fulfilment, report delivery and retained account access.

The owner has approved the reports and commercial launch. These are technical
and operational blockers, not a request for another product approval.

## References checked

- https://docs.stripe.com/payments/checkout/use-manual-tax-rates?ui=full-page
- https://docs.stripe.com/tax/tax-rates

Stripe currently labels dynamic_tax_rates deprecated and warns that unmatched
countries receive no rate. Do not treat that shortcut as a complete overseas
tax implementation.
