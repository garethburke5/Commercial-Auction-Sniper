# Operational checkpoint — 4 October 2026

Resume by checking current main, Actions and production, not by repeating this build.

Public site: https://garethburke5.github.io/Commercial-Auction-Sniper/
Legacy analysis host: https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/

## Implemented and published

- Device My Auction Sniper: separate Save and Watch, saved searches, private device
  notes, bid targets, recent views, import/export and observed change history.
  Watch compares snapshots when the customer returns; email alerts are not active.
- Provider-backed account and owner-scoped API integration uses the existing
  Accounts store, Supabase verified identity and server entitlements. It is gated
  until the private service and provider configuration exist.
- Commercial Deals public section with real auction spotlights, transparent
  labels and owner form. Owner draft preview works without publishing invented
  stock. Authenticated CRUD, enquiries and metrics have server implementations.
- Property market context uses the existing corpus, conservative full-address
  history and use/occupation/location/tenure comparable selection. Guide and
  actual sale result are distinct.
- Acquisition Intelligence: structured snapshot/full reports, source evidence,
  bounded ZIP ingestion, calculations, report-bound purchase/webhook access,
  owner-only retrieval/download and refund revocation. Current/historic lease
  amounts remain source-bound; document age is not proof of supersession.
- Source coverage page and JSON reconciliation; the Pages workflow compares every
  deployed search-index ID against the production snapshot and uploads proof.

## Live UI verification already performed

Desktop and a 390px phone viewport: Save/Watch remain independent; notes and a bid
price survived reload; a saved search reopened correctly. Owner draft preview
calculated 14% from £35,000/£250,000; mobile overflow was corrected and verified
at 390px. Commercial Deals labels and real comparable evidence were inspected.
All ten Barnett Ross lots were customer-findable after the first production repair.
Do not repeat those implementations.

Later browser access timed out during Streamlit sign-in. Recovery and reset also
failed. Therefore the newer Streamlit analysis interface has NOT been confirmed
live. HTTP/deployment checks are not a substitute for that visual verification.

## Current source fixes to verify in production

- `9cecc15d`: Bond Wolfe advertised-sale discovery replaces a hard-coded September
  date. The official 22 October catalogue exposed 173 lot URLs, all traversed
  successfully. Every detail is classified; terminal cards are retained.
  Residential flats and demolished pubs offered as housing sites remain excluded.
  The collector records per-lot outcomes, source/parsed counts and rejections.
- Explicit telemetry added to Auction Estates, Harman Healy and Future Property
  Auctions. Remaining unknown upstream stages must stay null, not invented zeroes.
- `603ab7ab`: Barnett Ross missing tenancy schedules recovered from the exact lot
  PDF; current concessions are not replaced by higher contractual rent. Primary
  retail use is not overridden by ancillary offices or nearby occupiers.
  Source checks: Worthing £13,600 p.a.; Loughborough £16,540 p.a., holding over.
- Both commits are on main. Follow the production runs and their subsequent Pages
  deployments; verify regenerated `data/properties.json` and the live search index.
  Do not call a source fix complete merely because its code is merged.

## Validation and boundaries

600 regression tests plus 8 subtests passed before the final licence-classification
regression. Retained Wrexham evidence: 22 documents / 276 pages, 73 OCR pages and
one unread page; 16 consolidated findings; no fresh 22-PDF extraction claimed.
An alterations licence is supporting evidence, not another occupational lease.

Accounts, paid reviews, subscriptions and live owner publishing still require the
specific provider/host inputs in `ACTIVATION.md`. Never claim these are activated
because their handlers or tests exist. No real customer payment has been taken.
No private legal-pack files or secrets have been committed.

Automatic historical collection remains active. Do not rebuild or restart it;
re-read persisted `data/auction_history/progress.json` for current counts.

## Next execution

1. Finish the pending source publication/live verification and inspect any real
   blocker in its logs. Do not launch duplicate full scans while one is running.
2. Restore browser access and complete Streamlit deployment verification.
3. Activate the existing private service with owner-supplied provider configuration;
   exercise signup, report purchase/refund and owner listing flows in sandbox.
4. Continue measured upstream telemetry for the remaining configured source estate.
   Null stages and degraded sources are still outstanding, not complete coverage.
