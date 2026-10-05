# Operational checkpoint — 5 October 2026

Resume by checking current main, Actions and production, not by repeating this build.

Public site: https://garethburke5.github.io/Commercial-Auction-Sniper/
Legacy analysis host: https://commercial-auction-sniper-ghihjbov2hgex6ci7zqklg.streamlit.app/

## Current customer-product course correction (supersedes the device access model below)

- Search keeps its normal Search → Refine → Results flow. Save this search is a
  contextual action after meaningful criteria are applied; naming happens in a
  dialog for entitled members, never in a permanent search-form row.
- Card Save/Watch controls sit beside the lot number; the property research link
  remains the primary action. Anonymous Save explains free registration. Watch
  and saved-search clicks show membership value and Plans & Pricing.
- Configurable public offer: Free £0, Premium Investor £15/month, Professional &
  Business £25/month in `plan_catalogue.json`. Explicit activation information
  remains separate from the named tiers. No invented report allowances.
- Registered Save remains free. Server checks require paid entitlements for Watch,
  saved searches, private-note editing and saved bid targets. Expired membership
  pauses event generation, while retaining data and allowing removal/clearing.
- Free accounts can still buy their own Full Acquisition Review without any
  subscription; owner/report binding is regression-tested.
- Acquisition Intelligence now leads with investor terms, costs, risks and
  opportunities, ZIP/multiple-document input, free Snapshot + Deep Dive and PAYG
  full review. Remaining questions follow the analysis.
- Existing device records remain readable/exportable; they cannot grant paid
  entitlements. Account, private-service and Stripe activation inputs still apply.
- Published code revision `9ce9083fc7dbeef756943c34b9ece51627135bfc` through
  successful Pages run `37261012916`, including all 82 publication-suite tests
  and source-to-live verification. No concurrent platform edits were overwritten.
- Live browser verification, 5 October: initial search has no saved-search row or
  contextual action; applying `Admiral` returns four lots and reveals Save this
  search. Its membership dialog, the separate paid Watch dialog and free-account
  Save dialog all work. Compact card controls remain beside the lot number.
  Plans & Pricing shows £0/£15/£25, separate PAYG and an honest activation boundary.
  Acquisition Intelligence uses the investor-focused proposition. Search, dialogs
  and pricing were checked at 390px; document width equals viewport width, with
  no horizontal overflow. These UI checks do not imply live provider activation.
- No new historical/source expansion was launched for this correction.

## 5 October afternoon continuation — regional coverage and income evidence

- `6384b3ed1dba678d8a312751f069aeddd030b09f` extends the existing Auction House
  regional collector to current homepage catalogues and online lot routes; hydrates
  all discovered categories before classification. Midlands, Kent, South Yorkshire,
  Northern Ireland and Oxfordshire are configured through the existing collector.
  Essex shares East Anglia; Notts/Derby and Staffordshire storefronts share Midlands.
  Other canonical regional lot links remain owned by their original regional feed.
- Source registry records evidenced family/region relationships separately from
  inventory equivalence. Eddisons/SDL/Mark Jenkinson unique inventory reconciliation
  is outstanding. New candidate auctioneers are assessments, NOT captured coverage.
- Explicit storefront advertised/discovered/parsed/rejected/fallback counts prevent
  silent zero/completeness claims. Partial identifiable commercial lots survive with
  unknown dates null. Shared online URL/date duplicates retain source-brand evidence.
- Financial normalization separates hypothetical/post-conversion income from current
  passing rent. Composite shop/residential/ground-rent components retain source text;
  ambiguous decimal source totals are only corrected with matching component sums.
  Current GIY excludes potential and historic-only rent.
- Public property pages reuse already-banked exact-address/postcode observations for
  guide/rent/tenant/lease/status timelines; capture time is explicitly distinguished
  from transaction time. Historic sale yield requires a recorded actual sale and
  passing rent. Comparable material differences are shown when evidenced.
- Homepage upcoming auctions count actual captured rows, and hide on refined search.
  Individual target-yield tool starts blank; user input still calculates the price.
- Final combined regression suite: 668 passed plus eight subtests. The exact Pages
  publication gate passed 85 tests. Full export: 1,552 pages.
- Pages run 37336848297 succeeded with source-to-live ID verification. Live HTTP
  inspection confirms four upcoming cards, no permanent search-naming row, and
  Plans & Pricing £0/£15/£25. The browser service timed out twice, so NEW desktop/
  mobile visual verification remains outstanding; do not claim it was performed.
- Publication run 37336848982 revalidated/published existing facts successfully as
  `294ccaba8`; full refreshed collector scan was still running at this checkpoint.
  Re-read its result and production/live snapshots before claiming recovered lots.
- Production re-read found two stale part-let statuses despite explicit source
  Occupation: Vacant. Added regressions for potential rent ranges/monthly equivalents
  and made that explicit source field clear unsupported current income.
- Live verification now compares guide/yield/status fields as well as IDs and
  collection time: financial revalidation deliberately retains both, so ID-only
  checks had allowed a stale financial index to pass.
- Derived-fact-only pushes revalidate and publish without launching another full
  source scan. Collector-route/configuration changes and manual runs still collect.
- Earlier Streamlit owner authentication request timed out. Its analysis UI remains
  unverified/stale; do not reset browser credential protection to bypass this.

## Earlier implemented and published work

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

On 5 October browser access recovered. The public embedded and standalone
Streamlit analysis workspace visibly still says “Analyse a legal pack”, whereas
current main's `buyer_due_diligence.py` says “Auction Sniper Acquisition
Intelligence”. Therefore that deployment remains stale; the newer analysis has
NOT been verified live. Streamlit Community Cloud is signed out and needs owner
authentication to inspect its configured branch/entry point and deployment logs.
Do not restart harvesting or report the newer analysis as live from repo tests.

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
2. Complete owner Streamlit sign-in, inspect its actual deployment configuration
   and logs, repair the stale analysis deployment, then verify its report flow.
3. Activate the existing private service with owner-supplied provider configuration;
   exercise signup, report purchase/refund and owner listing flows in sandbox.
4. Continue measured upstream telemetry for the remaining configured source estate.
   Null stages and degraded sources are still outstanding, not complete coverage.
