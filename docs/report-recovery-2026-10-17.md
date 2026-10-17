# Report recovery checkpoint — 17 October 2026

## Current operational evidence

- The Stripe connector now reaches AuctionMash sandbox `acct_1UO22H2MK0UQoSLq`.
  Its existing QA subscription and persisted Pro/Investor allowances agree. The
  sandbox webhook is enabled with all 14 event types handled by the backend.
  Clock advancement and invoice retry are not exposed by this connector, so
  actual failed-renewal/recovery acceptance remains outstanding. No live billing
  operation was performed.
- The scheduled catalogue check completed at 17:27:43 UTC: 37 healthy sources,
  408 rows withheld by source-health controls, zero eligible watched accounts.
  This verifies scheduled monitoring, not customer email delivery. Email alerts
  remain inactive.

## Interrupted report correction

The account report endpoint now reflects the durable processing record. An
ongoing or failed investigation no longer looks like an untouched snapshot ready
to start. A verified purchase hides additional purchase/redemption controls,
including while processing is underway or the attempt limit is exhausted.

The existing owner panel includes interrupted report recovery. A job must be at
least one hour old, remain on the specified processing attempt, and have fewer
than three attempts. The owner must inspect the old process/provider activity and
explicitly confirm that the worker has stopped. Time alone is not evidence of
termination. Recovery never calls a provider or changes a purchase/credit; the
customer returns to the same report and reattaches documents to retry.

Completion and failure writes are transaction-locked and checked against the
current attempt. Late old workers cannot replace a newer report or reset its job.
The old attempt remains interrupted, with recovery audit metadata and any late
usage measurements. Unknown usage must be reconciled with the provider, never
treated as a zero-cost report. Recovery does not reset the three-attempt limit or
release a report held for source-quality review. No schema migration is needed.

## Validation and limits

49 focused local tests passed: report processing/intake, credit controls and
account navigation. Regressions cover ownership, recent/changed/exhausted jobs,
duplicate recovery, retained entitlements, and late provider success or failure.
Hosted PostgreSQL tests exercise concurrent recovery; browser checks cover the
owner confirmation control at 360, 390, 430 and 1440px. Their results and the
deployment must be verified separately; local Chromium was unavailable.

This does not establish live AI report quality, measured generation costs,
production backup restore or customer inbox delivery. No production report job
has been reset. Live billing and paid reports remain closed.
