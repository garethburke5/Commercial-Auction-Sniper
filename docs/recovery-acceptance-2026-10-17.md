# Recovery acceptance — 17 October 2026

## Current evidence

The existing isolated PostgreSQL recovery test exercises pg_dump and restore of synthetic data. It now includes Auth user identity alongside report ownership, paid-credit periods and redemptions, email opt-out and an unknown email-provider outcome. The same Auth issuer and subject must recreate the same application account ID after restoration. The test rolls back its destructive drill and is restricted to localhost/auction_test.

This does **not** prove a production backup exists or can be downloaded/restored. The fixture's Auth table is a minimal projection; it does not run Supabase Auth or prove password sign-in, signing-key/session recovery or recovery of uploaded files.

## Production gate remains open

Before launch, record the actual backup method, latest successful timestamp, retention, encrypted storage location, who can restore it, and a measured recovery drill. The current connector cannot inspect/download managed backups. Do not infer backup availability from a healthy database or use a project unpause operation as a restore.

The recovery scope must cover:

- Private accounts, Stripe customer/subscription references, paid periods, purchases, redemptions, report records and generation-attempt history.
- Supabase Auth identities and the supported Auth recovery procedure. Changing the issuer/project URL changes the application's identity hash: a cross-project recovery needs an explicit, tested ownership migration. Never silently relink purchases by matching email addresses.
- Uploaded legal packs and generated document storage, if durable storage is configured, including their keys and retention policy. Database dumps do not by themselves restore object contents.
- Email consent, unsubscribe tokens, outbox and receipt records. Before starting any restored worker, disable alert sending, live billing and automatic report processing.
- Deployment configuration, webhook signing secrets and supported secret recovery, held privately outside the repository. No credentials or customer backup may be committed to git.

After restore, reconcile Stripe events and report-provider outcomes since the backup boundary before processing new credits or retrying jobs. Do not clear idempotency records. Any attempted email whose outcome is unknown and older than the provider's retry window stays stopped for manual reconciliation.

Acceptance must include an authorised test account signing in, reopening its purchased report, checking credit balance, verifying another account cannot access it, and confirming an opted-out account remains opted out. Record recovery point/time and observed results without including customer records or secrets in the evidence note.

## Source continuity check

The earlier permanent-history timeout is not a current outstanding failure: Bank Published Auction History run `39050983043`, started 17 October 2026 at 16:48 UTC, completed successfully following public publishing run `39049093201`. This is source-history continuity, not a backup of customer accounts.
