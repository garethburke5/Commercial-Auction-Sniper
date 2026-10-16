# Scheduled monitoring activation — 16 October 2026

This extends the existing Watch and saved-search worker. It does not send emails,
start paid analysis or change membership/billing entitlements.

## Runtime protections

- `/api/internal/monitor` accepts only a five-minute HMAC signature for that
  exact method/path, using a dedicated monitoring key. Public requests fail
  before accessing account services. Cron does not carry a reusable bearer key.
- A private database lease prevents simultaneous batches; completed checks have
  a ten-minute cooldown. An expired interrupted lease can be retried. Failures
  record only an error class and retain earlier observations.
- The worker fetches the fixed canonical GitHub snapshot, with a 25 MB limit,
  freshness and publication checks, and catalogue parsing before atomic install.
  Customers and scheduled checks then use the same refreshed file.
- Older Watch observations cannot replace newer ones. Private deal changes remain
  independent of public collection freshness. Saved-search archive exclusion,
  source-health protections and transaction deduplication remain in force.
- `/api/admin/monitoring` exposes aggregate last-run status only to the verified
  owner. Public scheduler responses contain no customer records or counts.

## Infrastructure

The existing Supabase project has the private `monitoring_jobs` table, RLS and
backend-only grants. `pg_cron` and `pg_net` are enabled. The invoker-only function
`auction_private.invoke_monitoring()` is executable by the database owner, not
public/anon/authenticated/auction_api roles. It uses the signing key in Vault to
create short-lived request signatures. The same dedicated key is configured in
Render without changing other environment variables.

No paid service has been added. Do not expose `auction_private` via PostgREST.
The scheduled invocation must be enabled only after the new backend endpoint is
live and a signed invocation completes successfully.

## Verification / rollout record

47 local tests passed across monitoring activation, saved-search matching,
Watch, membership and startup. PostgreSQL job claims/recovery are included in CI.

The earlier Watch/search/report-cost release was manually submitted for Render
deployment through the dashboard after multiple newer commits failed to trigger
an automatic deploy. Runtime success must be checked separately from build success.

Pending: publish this revision, hosted tests, deploy, signed invocation, cron
activation, observed scheduled success. Email-alert delivery remains inactive.
