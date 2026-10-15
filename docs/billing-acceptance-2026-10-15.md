# Auction Geek launch acceptance — 15 October 2026

## Verified deployed sandbox behaviour

Stripe sandbox only. Synthetic QA customers had no email addresses. The owner's
existing Pro membership was not cancelled, refunded or downgraded by these tests.
Assertions below were checked against Stripe and the deployed private PostgreSQL
records after actual signed webhook delivery; no entitlement rows were manually
seeded. Only synthetic account-to-customer bindings were inserted for isolation.

| Check | Result | Evidence |
| --- | --- | --- |
| Initial Pro payment | DONE | Stripe active subscription; deployed subscription active/professional; one funded period with allowance 3. |
| Cancel at period end | DONE for scheduling | Stripe cancel_at_period_end true; subscription and funded allowance remained active for the paid period. Automatic expiry at renewal remains unobserved. |
| Refund | DONE for membership-credit funding | Full £25 sandbox refund succeeded; signed charge webhook changed the funded period to payment_review. Further redemptions are blocked by the existing credit access query. |
| Cancellation | DONE for immediate cancellation | Stripe cancellation reached the deployed database as canceled. This excludes paid membership privileges and unused credits. |
| Failed initial payment | DONE | Stripe's attachable decline test method produced an incomplete Investor subscription; deployed database recorded incomplete and zero funded report periods. No paid tier is granted for incomplete status. |
| Test cleanup | DONE | Successful test subscription canceled and refunded; failed test subscription canceled to incomplete_expired. Retained synthetic records provide an audit trail. |
| Downgrade policy | PARTIAL | Default sandbox portal schedules decreasing_item_amount changes at period end; a full scheduled downgrade through renewal is not yet verified. |
| Renewal/no rollover | PARTIAL | Automated transaction tests cover period expiry, reduced next-month allowance and no rollover; actual clock-advanced Stripe renewal remains outstanding. |
| Returned purchased report | PARTIAL | Ownership and survival after cancellation are covered by software tests. Real generated report download/logout/return acceptance remains outstanding. |

The connected Stripe tool exposes test-clock creation but not clock advancement,
and exposes schedule reads but not schedule writes. Do not mark renewal or
scheduled downgrade complete merely because the configuration exists.

## Additional checkout safeguard

Two old subscription checkout sessions were still open for the owner's already
subscribed account. Billing now expires owned, open subscription checkouts when
a subscription becomes active and when an existing subscriber requests checkout.
It preserves one-off report sessions and sessions for other account references.
Cleanup failures leave the webhook unacknowledged so Stripe can retry. Already
expired sessions are safe to replay. Concurrent completed payments cannot be
undone by checkout expiry and would require billing review.

Validation: 30 focused tests passed, including nine cleanup cases and the 21
existing report-credit tests. Hosted CI and deployment verification are separate
from these local results.

## Investment Report quality and costs

- The deployed report_generation_attempts table contained zero rows and zero
  measured attempts at this check. No actual hosted report cost or margin can
  therefore be claimed.
- The existing evidence replay covers Newbury with a pack (38 documents), Newbury
  without a pack, and Maybrey without a pack. Its own manifest explicitly states
  zero provider calls, incomplete review and paid_approved false for every case.
- Remaining evidence issues include substantive investment conclusions, local
  rental sustainability, environmental evidence, condition/expenditure, and
  source dispositions. Newbury's exact-demise EPC coverage and listed-building
  implications remain required real-output checks.
- The existing provider factory requires OPENAI_API_KEY, ACQUISITION_MODEL and
  ACQUISITION_PROVIDER=openai. Actual cost estimation additionally needs a dated,
  model-matched ACQUISITION_COST_RATES_JSON. Secrets belong in the backend secret
  settings, never public code or this document.
- Monthly revenue before payment fees, tax, overhead and other subscription
  features is £15 per included Investor report, or £25/3 (about £8.33) per included
  Pro report when all credits are used. These are revenue ceilings, not margins.
- Paid reports remain closed. Fresh investigations through the existing provider
  must be assessed with and without packs before approving quality or pricing.

No live billing activation, quality approval, new report engine or customer email
was performed by this acceptance pass.
