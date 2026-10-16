# Saved-search launch checkpoint — 16 October 2026

## Implemented

- Reuses saved searches, membership entitlements, account identity and the private
  monitoring worker. No new authentication or reporting engine.
- Criteria match Find Property: all keyword terms, source/brand selections,
  tenure, availability, guide-price limits and conservative income yield.
- First healthy observation establishes a baseline for each source, without
  reporting the existing catalogue as new. Later newly qualifying lots appear
  under the customer's saved search in My Auction Geek (ten latest per search).
- Only current searchable catalogue rows are eligible; archive rows are excluded.
- Locks serialize concurrent checks and edits. Repeated or older snapshots cannot
  produce duplicate matches. Degraded/stale sources preserve earlier baselines.
- Membership expiry pauses detection and display. Criteria edits clear that
  search's baseline/history; deletion clears its monitoring data. Every read and
  write is scoped to the verified account ID. Email remains inactive.

## Verified

40 focused local tests passed, including application startup, matching parity
against the actual browser keyword/numeric matcher, simultaneous checks, outages,
expiry, archive exclusion and account-isolated edit/delete.

The additive production database migration `private_saved_search_monitoring`
succeeded. Both tables are in `auction_private`, have RLS enabled, deny direct
anon/authenticated access and permit only the existing backend access role.
No customer records or credentials were changed. Security advisor reported no
new table warnings; existing leaked-password protection remains disabled
([Supabase guidance](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)).

PostgreSQL concurrency and browser checks at 360/390/430/1440px are included in
GitHub CI; their result must be recorded after this revision is published.

## Still partial / blocked

Render was verified still serving `62012b58`, despite automatic deployment being
configured for commits to main. Production database readiness does not mean this
backend change is deployed. Deployment freshness needs resolution.

The worker can check searches without a browser, but a hosted schedule is not
active. Actual alert email delivery, verified recipients/consent, retries and
inbox acceptance remain outstanding. No claim of operational email alerts.

AI provider configuration, actual with/without-pack report quality/cost approval,
remaining Stripe sandbox lifecycle acceptance, source reconciliation and complete
launch acceptance remain open. Paid reports and live billing remain closed.
