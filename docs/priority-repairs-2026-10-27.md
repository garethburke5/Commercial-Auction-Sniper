# Priority repairs — 27 October 2026

## Account connection

The production build had empty Supabase/API Actions variables and silently
exported `accounts_enabled: false`. The existing backend is healthy and reports
accounts ready; the live public Supabase key accepts the authentication-settings
request, and both services accept the auctiongeek.co.uk origin. No email was sent,
no real account was created, and payment/report activation was not changed.

Commit b24adcef restores versioned browser-safe configuration for the production
site and its verification mirror, with environment overrides still supported.
Only a publishable key is exported. A partial override or server credential fails
the production build. Deployment verification now rejects disabled accounts even
when the live and built files match. Local configuration/export tests: 26 passed.
Live deployment verification is recorded separately; backend readiness alone does
not establish successful customer sign-in or email delivery.

## Social monitoring

Read-only Buffer inspection found six review posts scheduled outside the agent:
Colchester (Facebook/Instagram 28 October), Shipley (Facebook 29 October,
Instagram 30 October), Belsize Road (Facebook 30 October, Instagram 2 November).
Both channels are connected and unpaused. See marketing/README.md for exact times.

The old monitor attempted to undo those schedules because automatic publishing
was disabled. Commit 87a13caa distinguishes externally scheduled review posts
from schedules created by the agent, preserves the former and records evidence
warnings without silently cancelling them. Explicit pause remains effective.
New agent schedules still require both approval gates and a durable intent.

Run 40551478591 passed 81 tests and completed live reconciliation with 16 managed
posts and five API calls. Automatic publishing remains false. Scheduled status is
not proof of successful publication. Missing insights permission remains separate.

## Pugh current collection

The 12:10 scheduled scan left 16 detail pages unresolved because their responses
lacked the expected heading/particulars. All 16 exact URLs were retrieved again
and parsed successfully: they classify as residential or land, not additional
commercial stock. This resolves those omissions' classification; it is not an
increase in historical appearances or a full UK coverage claim.

The shared collector now retries only failed details once, at lower concurrency,
retains the failed URLs/reasons, and counts recovered pages once. Index failures
also prevent a misleading LIVE status or complete denominator. The transport
already has bounded HTTP retries; this additionally recovers HTTP-success pages
that fail content validation. 32 Pugh regression tests passed. The complete live-source verification then
finished successfully: 22 catalogue pages, 374 detail pages inspected, 89
commercial/mixed-use lots (87 available and two unavailable), 285 noncommercial
lots excluded, zero unresolved detail/index failures. No retry was needed in
that successful pass. This is a local live-source check; the production scan
40553104562 is separately responsible for publishing its refreshed snapshot.

## Investment-report defects

The retained Surbiton extraction was replayed through the current engine after
matching all 11 document hashes to saved originals/recorded converted files.
This was not new OCR, new market research, an untouched holdout or a provider run.
No paid AI calls were made.

A generic `£... per annum` match incorrectly treated the £4,500 service-charge cap
as rent, creating a false £4,500/£58,500 rent conflict. The shared extractor now
requires rent-clause context and rejects insurance/additional-rent costs. The
replay retains £58,500 as the rent observation and removes that false conflict.

Shared interpretation now explains evidenced seller percentage costs, service-
charge caps/indexation/cessation, and conditional renewal-rights exclusions.
Amounts must stay attached to their own evidence. The Surbiton cost remains
£17,581.20 at the £490,000 assessment price; it is not silently dropped from the
no-charge research update. A two-card truncation no longer hides material
findings, and short research updates keep sources at the bottom instead of
forcing an otherwise empty sources page. The two-page replay was visually
inspected; the paid product remains closed.

Remaining report blockers include matching the occupational lease and proposed
long lease to the property interests, resolving actual rent-uplift dates, title
and plan interpretation, supported market value/cost conclusions, and independent
commercial/editorial acceptance. Passing extraction or layout checks does not
establish that the full report is worth £19.

## Deployment checkout cost

The public workflows previously checked out over 130,000 raw source files. They
now exclude the raw source/catalogue/appearance directories and retained scratch
databases, while keeping the packaged history database and parts, properties,
progress and source-register metadata. Git sparse-checkout inclusion checks
confirmed these boundaries. This changes website checkout only; it does not
remove archived records or alter the historical collection workflows.
The full local report regression set passed 226 tests and three subtests.

## Historical checkpoint

The existing collector checkpoint at 17:30 UTC records 304,492 retained
appearances, including 89,430 classified commercial/mixed-use appearances.
There remain 515 incomplete/unreconciled catalogues and 22 fetch/parse failures.
These counts are not a claim of comprehensive national 20-year coverage.

## Verification after fixes

- Public release run 40553692197: 512 tests passed, 14 skipped and three
  subtests passed; controlled desktop/mobile browser checks passed. The GitHub
  Pages verification mirror exports the correct enabled public account config.
- Report CI run 40554984910: 261 tests and three subtests passed. It now explicitly
  includes test_legal_pack_review.py, including the service-charge/rent regression.
- Cloudflare checkout completed in 1 minute 24 seconds, compared with more than
  14 minutes for the obsolete full checkout. Production run 40553692197 subsequently
  completed its deployment and live verification successfully.
- Backend readiness still reports production_email_confirmed false, live billing
  false and paid_reports_approved false; no email delivery or paid acceptance
  claim is made. Its reported revision was 87dcbcc685fc5c3b45652fae4dc202eb4ca0979e
  at this check, so the new report-engine code is not yet verified on that backend.

At 18:00 UTC, auctiongeek.co.uk/deployment.json returned the tested
revision a7de524f574882efe9f405e1286e752efbfb8e09. Its platform-config.json
passed account validation with accounts_enabled true and billing_enabled false.
The repair is live; delivery of real customer authentication email remains an
independent verification item.

The production account page was also checked in Chromium: the email/password
sign-in form, account creation control and recovery options rendered correctly.
No real sign-in or email was submitted.
