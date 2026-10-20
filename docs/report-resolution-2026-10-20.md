# Rejected report settlement — 20 October 2026

Paid report approval remains closed. This change implements customer protection;
it does not establish the commercial quality of reports or approve sales.

- A completed customer investigation rejected by the shared acceptance checks
  records a rejection in the same fenced transaction as the result.
- A consumed report credit becomes one replacement credit. The original
  redemption remains in the audit trail and no longer unlocks the rejected report.
  Replacement credits survive monthly expiry/cancellation but require the
  original invoice to remain paid. Ordinary unused monthly credits still expire.
- Concurrent claims cannot spend one replacement twice. Rejection of a replacement
  returns one credit again, without increasing the original allowance.
- A one-off report payment enters a durable refund outbox. Current Stripe
  customer/order/payment/dispute state is checked before refund submission.
  Idempotency and metadata reconciliation cover a lost response after submission.
  Pending refunds are not presented as completed. Payment-review cases remain held.
- Refund attempts run on completion and through the existing signed monitoring
  schedule. The owner-only retry endpoint is `/api/admin/report-refunds/retry`.
- The third failed processing attempt also settles funding. Earlier failures
  retain the entitlement for bounded retries. Repeated requests cannot restart a
  rejected report or charge for it again.
- An included pack update does not refund the already delivered original report.
  Owner validation cannot mint credits or cash-refund claims.

Validation: 274 platform tests passed locally; 12 PostgreSQL-dependent tests
were skipped without the disposable database. Nine new resolution tests cover
concurrency, membership expiry, renewal, disputes, ownership, remote timeout
reconciliation and the API rejection path. A separate PostgreSQL regression is
included for hosted CI. Production schema is additive and private, with RLS and
no browser-role access. Actual Stripe sandbox refund acceptance and the complete
paid report journey remain required before paid launch.
