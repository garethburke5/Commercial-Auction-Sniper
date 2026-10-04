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

## Source publication checkpoint

- `9cecc15d`: Bond Wolfe restored and verified in production and the public site:
  173 source lots, 173 parsed, 25 qualifying/live (13 commercial, 12 mixed-use),
  148 classification exclusions, zero quality rejections and zero live discrepancy.
  The official 22 October catalogue is discovered dynamically. Both Sold Prior
  properties remain visible. Residential flats and housing redevelopment sites
  stay excluded. Every catalogue detail is examined, not just commercial teasers.
- Explicit telemetry added to Auction Estates, Harman Healy and Future Property
  Auctions. Remaining unknown upstream stages must stay null, not invented zeroes.
- `603ab7ab`: Barnett Ross missing tenancy schedules recovered from the exact lot
  PDF; current concessions are not replaced by higher contractual rent. Primary
  retail use is not overridden by ancillary offices or nearby occupiers.
  Persisted production and public property checks: Worthing £13,600 p.a.
  (10.5% GIY at £130,000); Loughborough £16,540 p.a. (9.5% at £175,000),
  Oxfam holding over. The designated source hero and yield calculator remain.
- `3358733c`: McHugh now discovers its current catalogue from `/current-auction`,
  examines all lot details and records per-lot outcomes. The obsolete fixed sale
  ID/date are removed; generic bidding-help status wording cannot change a lot
  status. Production run 37217057723 completed, but every first-party entry route
  returned empty responses. McHugh remains DEGRADED with zero live stock; do not
  claim its restoration or try to evade an access restriction.
- `d9b604ce`: tenant-brand wording no longer overrides an explicit retail subject.
  The live 1133 Warwick Road page was checked: Retail investment, guide £550,000
  and current rent £78,800. Unmeasured collector residential exclusions stay null
  and are separate from measured publication-stage exclusions.
- Full deployed-index comparison at snapshot 2026-10-04T17:06:09.750427+00:00:
  968 expected and 968 live IDs, zero missing/unexpected IDs and zero duplicates.
  Current proof schema is 2; see `data/source_live_verification.json`.
  Production run 37217057723 and Pages run 37219278839 both succeeded.
  Barnett Ross has ten published/live properties; Bond Wolfe has 25.
- Seven sources remain honestly DEGRADED: Auction House Wales (detail fallback),
  Barnard Marcus (one detail failure), Harman Healy, LSH, McHugh, Paul Fosh and
  Town & Country (transport/discovery failures on the latest run). Previously
  collected current stock is preserved where available; McHugh has none.
  Site/transport failure is not collector restoration. Do not weaken admission
  or invent upstream counts. Further upstream telemetry remains incomplete.

## Validation and boundaries

609 regression tests plus 8 subtests passed, including the final licence, income,
McHugh route/status and reconciliation regressions. Retained Wrexham evidence: 22 documents / 276 pages, 73 OCR pages and
one unread page; 16 consolidated findings; no fresh 22-PDF extraction claimed.
An alterations licence is supporting evidence, not another occupational lease.

Accounts, paid reviews, subscriptions and live owner publishing still require the
specific provider/host inputs in `ACTIVATION.md`. Never claim these are activated
because their handlers or tests exist. No real customer payment has been taken.
No private legal-pack files or secrets have been committed.

Automatic historical collection remains active. Persisted production at this
checkpoint: 200,803 appearances, 28,717 commercial and 26,863 mixed-use; these
are automatic corpus totals, not manual additions claimed for this batch.
Do not rebuild or restart harvesting. Re-read
`data/auction_history/progress.json` for current counts.

## Next execution

1. Check current main, live generation and Actions before acting. Previously
   triggered source scans can still be queued/running; do not launch duplicates.
   Follow up the actual degraded source stages, especially McHugh transport.
   Deployments create fresh reconciliation artifacts automatically; persisted
   live proof is only displayed when its generation matches the current snapshot.
2. Restore browser access and complete Streamlit deployment verification.
3. Activate the existing private service with owner-supplied provider configuration;
   exercise signup, report purchase/refund and owner listing flows in sandbox.
4. Continue measured upstream telemetry for the remaining configured source estate.
   Null stages and degraded sources are still outstanding, not complete coverage.
