# Launch priorities checkpoint — 12 October 2026

Stripe account activation is reported complete by the owner. This does not yet
prove the website's sandbox checkout or server credentials. Live billing and the
paid-report quality gate remain disabled.

## Verified in this work session

- Render release `08e9fa4cecd99022aa927a01f0c2ba607bbed50c` is live, deployment
  `dep-db6carnlk1mc73cnugh0`, finished 11:39:36 UTC. Application logs confirm
  private-API mode, 1,787 catalogue properties, and successful port binding.
  Factory startup took 40.50 seconds on the existing free instance. The earlier
  release had timed out before opening a port. This proves process startup,
  not an authenticated customer journey.
- Local before/after catalogue comparison: 23.271 seconds to 3.220 seconds for
  the same 1,780-property fixture; every record, current-property ID and source
  mapping was unchanged. Removed quadratic sentence scans and repeated
  commercial-use classification without relaxing publication rules.
- Permanent-history run `38212116354`, retry job `114791405175`, succeeded.
  The history build/validation took about three seconds, previously exceeding
  twenty minutes. Published commit `fc436d0965f87a39bcaa363ad60026da3ec2084f`
  contains 24,152 properties and 25,364 auction events, all with source URLs.
  Postcode indexing preserves the existing confidence threshold, variants,
  neighbouring-property separation and tie order. Deep backfill remains deferred.
- Local platform/history suite: 141 passed, six PostgreSQL checks reserved for
  CI. The hosted PostgreSQL check on `08e9fa4` passed, as did public publishing
  and Cloudflare deployment.
- All 18 Supabase private tables have RLS and deny direct reads to `anon` and
  `authenticated`. Auth currently contains zero users. The existing Stripe
  sandbox currently contains zero Checkout Sessions. Neither is customer
  acceptance evidence.

## Further fixes in this checkpoint

- Shared account API/upload/download requests reject responses after an account
  transition, including sign-out followed by returning to the same account.
  Stale callbacks cannot restore the previous private workspace. The 13 real
  JavaScript adapter tests pass; these are controlled session tests, not actual
  email sign-ins.
- Permanent-history updates fail on corrupt existing data and write through a
  flushed temporary file followed by atomic replacement. Tests verify that a
  failed replacement preserves the last good file. This is a publishing safety
  improvement, not a production database backup or restore drill.
- Account visits reuse the loaded catalogue while its file identity, size and
  modification/change times are unchanged. A replaced or edited snapshot is
  loaded once under a lock; freshness and source-health are still checked on
  every visit. Tests cover reuse, replacement, stale/degraded input and recovery.

## Secure configuration follow-up

Render dashboard sign-in completed successfully. The runtime environment has the
existing Stripe prices and webhook secret but no `STRIPE_SECRET_KEY`. There is
also no `OPENAI_API_KEY`, configured acquisition model/provider, or
`ADMIN_ACCOUNT_IDS`. These are confirmed missing settings, not inferred from
account activation. No secret values were revealed.

The deployed health-check path is now `/healthz`. Render redeployment
`dep-db6d21h42hec73bpt770` succeeded at 12:25 UTC, with repeated HTTP 200 health
checks in its application logs. The shared-client isolation/history-write commit
`5fe014db1c63591710244b21286a5441ee0907d1` passed PostgreSQL CI, public publishing
and Cloudflare deployment.

## Remaining acceptance by priority

| Priority | State | Remaining evidence or work |
| --- | --- | --- |
| 1 Backend | PARTIAL | Startup and health check fixed/live. Verify account readiness and public-to-private requests with actual sessions. |
| 2 Accounts | PARTIAL | Production sender configuration, delivered sign-in links, actual persistent customer sessions and isolation. |
| 3 Owner | BLOCKED | Register and verify the real owner, then bind the verified ID and test all previews. No owner ID is inferred or fabricated. |
| 4 Stripe | PARTIAL | Owner activation reported complete; sandbox runtime key, Checkout, signed deliveries, renewals, cancellations, failures and refunds still need deployed proof. |
| 5 Report quality | BLOCKED | Configure the existing AI provider securely; generate fresh real-property reports both with and without packs and independently approve the outputs. Resolve the Newbury-specific evidence issues. |
| 6 Costs/access | PARTIAL | Attempt accounting exists; measure actual provider/processing costs, approve update/retention policy, prove return/download and access after cancellation. |
| 7 Watch/alerts | PARTIAL | Account event tracking exists. Monitoring worker explicitly does not send email; actual scheduled checking and email delivery remain to activate. |
| 8 Data | PARTIAL | Current-history banking repaired and published; finish current-source coverage reconciliation. Historical expansion stays deferred. |
| 9 Safeguards | PARTIAL | Hosted test-database checks passed. Production backup/restore including Auth, interrupted report-job recovery, retention terms and complete desktop/mobile acceptance remain open. |

Render's connector supports environment updates but does not expose a read of
the deployed environment; its dashboard was used after secure sign-in. Do not
request passwords or server keys in chat, invent a customer identity, enable
live charging, or treat code/tests as deployed customer acceptance.
