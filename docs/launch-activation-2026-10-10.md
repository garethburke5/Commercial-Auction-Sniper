# Account activation and investigation runtime: 10 October 2026

## Changes and boundaries

The existing Python API now accepts `ACCOUNT_DATABASE_URL` for permanent private
PostgreSQL storage. SQLite remains supported for local work or a mounted disk.
Existing account IDs, permissions, payment records, report ownership and owner
previews are reused. No parallel customer-account system was introduced.

`web_platform/private_schema.sql` creates a non-exposed `auction_private` schema
and a restricted `auction_api` role. Browser anon/authenticated roles have no
schema or table access. Every table has RLS, with access for the backend role
only. Customer isolation remains enforced by the verified-identity API. The role
initially has NOLOGIN; provision its application credential securely, never in
this repository. The live Supabase migration `private_account_storage` succeeded;
all 14 tables have RLS, neither browser role can read them, and the security
adviser returned no findings. A transactional save/update probe was rolled back.

The free Render configuration is `web_platform/render.free.yaml`. It reuses the
Supabase project and does not require a paid Render disk. `PRIVATE_API_ONLY=true`
avoids rendering the public website into the private process. Public pages stay
on the current static host. Render free sleep/cold starts make this a staging and
owner-testing setup; they are not an always-on paid monitoring promise.

A new CI job tests the actual PostgreSQL driver, durable writes, rollback,
concurrent processing claims, backend privileges, customer isolation and owner
preview controls against disposable PostgreSQL 17. Local SQLite and existing
account tests remain in place. `/api/readiness` reports non-sensitive activation
booleans, distinct from the liveness-only `/healthz`.

That PostgreSQL 17 CI run passed all 11 provider/storage checks on commit
`108a5a2`, including the restricted database login and concurrent job claim.
The wider local account/investigation suite passed 137 checks (four PostgreSQL
checks were skipped locally and exercised in CI). The free Render service is
`auction-sniper-private-api` (`srv-db52g3jbc2fs73e380ag`); its initial build
succeeded. The later owner-approved activation checkpoint below supersedes the
initial credential status; actual owner website sign-in remains unverified.

## Production research/review provider

`acquisition_provider.py` supplies a concrete OpenAI Responses adapter to the
existing investigation pipeline. Set `ACQUISITION_PROVIDER=openai`, an explicit
`ACQUISITION_MODEL`, and the server-only `OPENAI_API_KEY`. Without all three no
provider is activated. A fresh provider/budget belongs to each purchased review.
Instantiation and expensive execution happen after verified report purchase;
free snapshots and subscriptions alone still cannot trigger paid analysis.

The adapter reviews complete source records in bounded batches, records the
substantive disposition of each document and synthesises findings across the
whole investment. Changed research triggers resynthesis; unchanged source
batches can be reused within that review. Findings must quote their cited source
text; unknown references, omitted review coverage and incomplete provider output
fail closed. No property name or tenant brand is hard-coded.

The research adapter uses actual web-search actions, then independently captures
public source pages/PDFs before accepting structured facts. It rejects private
network targets, credentials in URLs, insecure schemes, oversized sources and
unsupported content. DNS is pinned to the checked public address with hostname
TLS validation. A source-access failure remains an explicit investigation limit.
Quoted and numeric facts are checked against the captured evidence. Source dates,
scope and asking/guide/achieved distinctions remain in the evidence contract.

Calls, input size, output tokens, searches, captures and elapsed time are bounded.
Actual provider token/tool usage is retained. Monetary cost/margin remains unknown
until reconciled with the configured model's current contracted rates; these
resource limits are not advertised as a guaranteed dollar spending cap.

A source review that remains incomplete is retained as `requires_review`, not
silently delivered as a completed paid report or rerun automatically. The global
Acquisition Intelligence quality gate remains closed.

## Still required before operational acceptance

- Actual restricted-login connectivity is verified below. Still exercise a
  real owner's saved account data across a restart as part of journey acceptance.
- Complete Supabase production email configuration and test an actual verified
  owner sign-in. Bind `ADMIN_ACCOUNT_IDS` to that account's verified issuer/sub
  hash, never its editable profile. Check all four read-only preview tiers.
- Enable public configuration only after the account journey works. The
  publishable Supabase key is public; database/API/payment keys are secret.
- Enter provider secrets directly into host settings. Run the concrete AI
  provider against the original Newbury pack and materially different packs;
  evaluate actual findings, omissions, commercial usefulness, cost and runtime.
- Verify sandbox Checkout/webhooks/cancellations/refunds and purchased-report
  revisit/download before any live billing. Stripe connection alone is not
  runtime authentication. No live charging or paid-product approval is implied.

The 39 original Newbury PDFs were recovered and SHA-256 checked against the
retained extraction: all 39 match. The older sale conditions remain superseded by
the amended set. This identity check is not a fresh full-pack analytical review.
Private documents and source extractions are not committed to this repository.

## Verified checkpoint after deployment

- Render deployment `dep-db52g4bbc2fs73e38360` reached `live` on 10 October.
  The service remains on the free plan. Public accounts have not been enabled.
- PostgreSQL/provider integration: 11 passed in CI. The legal-pack CI and the
  full publishing regression workflow passed after adding the adapter's HTTP
  dependency to the core requirements.
- The current deterministic pipeline was rerun against the retained original
  extractions for Newbury (540 pages), Wrexham (276), Maybrey (402) and Dover
  (450). Newbury's four identified rents reconcile; the other three remain
  unreconciled. These are replay/regression checks, not fresh autonomous
  investigation or investment-quality approval.
- Original Newbury lease pages and service-charge table were visually inspected.
  Overprinted lease dates still require evidence of the operative amendment;
  a table deficit is not automatically a buyer liability. No new specimen is
  described as approved or independently provider-validated.
- Supabase dashboard authentication succeeded. The actual shared-pooler host
  was retrieved. There are still no registered website users.
- At this initial checkpoint, automatic approval review rejected enabling login for the restricted
  `auction_api` role and provisioning its credential. The role remains NOLOGIN;
  no database credential was installed in Render. Explicit owner approval for
  that scoped backend access is needed. Do not retry through another route.
- Owner preview remains implemented and tested, but cannot yet be exercised
  against the real owner account. The production analysis provider still needs
  its API key and explicit model configuration in secure host environment settings.

## Owner-approved database activation — 10 October, afternoon

The owner explicitly approved the restricted backend login and secure Render
credential storage. Migration `activate_private_backend_login` succeeded. A
fresh generated application credential was saved only in the Render service's
`ACCOUNT_DATABASE_URL` environment setting; no credential is in this repository.
The existing database administrator password was not changed.

Readback confirms `auction_api` can log in and use `auction_private`, with no
superuser, create-database, create-role or RLS-bypass privilege and no access to
the `auth` schema. Browser `anon` and `authenticated` roles still cannot use the
private schema. The Supabase security adviser returned no findings.

The environment update automatically started Render deployment
`dep-db53pejbc2fs73e7m340`, which reached `live` at 13:37:42 UTC. Its application
log records `GET /api/readiness` returning HTTP 200 at 13:37:44 UTC. That route
returns 200 only after the account service opens its configured database and
successfully executes `SELECT 1`. Supabase also records an `auction_api` pooler
connection. This verifies actual runtime connectivity, not just saved settings.
Owner sign-in and per-account restart persistence remain separate acceptance steps.
The sign-in site URL and exact `/account/` redirect were verified in Supabase.
Custom SMTP is disabled, so public email registration remains unactivated.

The private API now avoids generating public opportunity summaries when loading
or refreshing its catalogue. It retains the same identifiers, source facts,
classification, yield and workspace observations. Public rendering still uses
the full summaries. The website/account suite passed 102 tests, with four
PostgreSQL integration tests reserved for the existing database-enabled CI job.
On commit `e204f20`, both the public platform workflow and private PostgreSQL
integration workflow passed (the latter exercises all 11 storage/access checks).

The current Render service uses a public repository URL rather than a connected
Git-provider credential. Such services require a manual deploy after code changes;
the API's `autoDeploy` flag alone is not proof that a push will deploy. The tested
catalogue optimisation requires a newer deployment than `dep-db53pejbc2fs73e7m340`.
No paid plan, additional service or production email provider was added.
