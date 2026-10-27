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
that fail content validation. 32 Pugh regression tests passed. A new complete
source run must establish the current counts before claiming live recovery.

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
