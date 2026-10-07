# Priority switch — 6 October 2026 (user instruction)

Do not add another historical auctioneer after Seel. Existing scheduled harvesting
and banking may continue; do not start new historical source expansion until the
following customer priorities are finished and live-verified, in this order:

1. Approved thin Upcoming Auctions strip above Search (approved mockup).
2. Current Auction House UK / North West reconciliation.
3. Current missing-source coverage: Wilsons, Sutton Kersh, Under The Hammer,
   iamsold, Edward Mellor, Cheffins and already-confirmed gaps.
4. Source-health / silent-zero protection.
5. Newbury Acquisition Intelligence report against improved main and stale
   Streamlit deployment (report 4f6afcc315519c90; supplied HTML, not the raw pack).
6. Outstanding customer-facing work.
7. Desktop/mobile live verification.

Do not restart completed course corrections or the corpus. The homepage currently
counts available lots separately from sold/withdrawn/postponed lots; the catalogue
includes both. The new results wording makes this distinction explicit.

## 6 October late evening — current coverage and report terms

- Added production-integrated current collectors for iamsold and Wilsons. No new
  historical auctioneer was added. iamsold: 275 unique details fully parsed,
  110 qualifying (68 commercial, 42 mixed-use), 165 classification exclusions,
  zero discovery/detail failures. Scope is its national commercial, hotel,
  garage/parking and land categories; residential categories are not claimed.
  Fixed the source pagination mismatch (10-item pager, 12-item actual pages),
  requiring reconciliation to each published category denominator.
- Wilsons: seven UK event catalogues, 37 advertised current records plus one
  ended record, all 38 parsed. One qualifying mixed-use opportunity; 36
  classification exclusions and one ended lot excluded. Source-designated images,
  guide ranges and visible lot statuses are preserved by both collectors.
- Publication candidate: 938 -> 1,049 rows. Source-health counts now reconcile
  AFTER outage preservation; count-collapse baselines survive revalidation.
  Undated rolling stock can survive an explicit source outage for no more than
  48 hours from actual collection. Do not describe stale evidence as fresh.
- Acquisition extraction now handles worded completion periods, deposit clauses
  containing condition references, lot-specific auctioneer fees and explicit
  seller no-option-to-tax statements. Conflicting fees/VAT stay unresolved.
  781 tests plus eight subtests pass. A recovered real seven-page Newbury
  conditions PDF was processed locally and its exact terms/calculations checked.
- Newbury source recovery: 37 of 38 documents match the supplied legacy report
  by SHA256. The recovered special conditions are a DIFFERENT version:
  seller costs £4,500 + VAT versus £2,000 + VAT in the report's original.
  Do not combine them or claim exact original-pack end-to-end verification.
  The newly recovered Lot 243 ZIP belongs to Shipley, not Newbury. No private
  documents or raw reports are committed. Need the original amended Newbury
  conditions/ZIP before that exact-pack sign-off.
- Pending after this batch: Cheffins current route, remaining degraded current
  sources (including UTH GitHub-runner 403), broader regional reconciliation,
  and provider activation for real accounts/payments. Existing owner Streamlit
  session is authenticated through GitHub; do not request sign-in unnecessarily.
  Publication/live outcomes below must be updated after checking deployment.

## 6 October live-product continuation

- Upcoming Auctions is now a thin rail ABOVE search, preserving the approved
  design. Desktop and 390px phone layout were opened on the public site; no
  page-wide horizontal overflow. Collection time is retained on revalidation.
- Auction House shared regional brands now participate in source counts and
  customer filtering without duplicating property rows. Six residential lots
  were quarantined after distinguishing nearby amenities/domestic studies from
  the actual accommodation. Public board verified at 905 rows (834 available,
  71 sold/withdrawn/postponed) before the next fresh scan.
- Current collectors added: Sutton Kersh (74 details, five qualifying), Edward
  Mellor (49 details, three qualifying), Under The Hammer (440 public records,
  224 past, 25 qualifying current). All are complete source traversals, not
  hard-coded property patches. Mellor two-day auction dates stay null unless
  the source supplies an exact individual lot day. UTH uses its official first
  image, separate from its floorplan. New rows require production/live validation.
- Fixed Publish Now deadlock: fresh collection runs BEFORE its candidate quality
  gate; old-snapshot revalidation is a separate path for derivation-only changes.
  Confirmed old failure explicitly named missing Sutton Kersh/Edward Mellor health.
  Superseded scan cancelled so the latest source revision can publish once.
- Confirmed current gaps are now included in reconciliation even before a
  collector is enabled. Unknown counts remain null. A zero qualifying result
  needs complete parsing/exclusion evidence; otherwise health is degraded.
- Wilsons: upcoming UK events/featured rows discovered, full catalogue traversal
  still outstanding. iamsold: national commercial discovery works, detail collector
  outstanding. Cheffins: main catalogue link refers to September; CPN/timed route
  network-denied from this runtime, current count unknown. No historical source
  expansion was started.
- Newbury supplied HTML 4f6afcc315519c90 is legacy Evidence review v2, not the
  current Acquisition Intelligence renderer. Live embedded Streamlit still shows
  “Analyse a legal pack”, while main shows “Auction Sniper Acquisition Intelligence”.
  Its board snapshot is 29 September. Exact legacy generating SHA is unavailable.
  Added engine release/content fingerprint to newly processed reports and UI;
  old reports never inherit a claim that today's engine processed them. The raw
  540-page Newbury pack is not supplied here, so no full reprocessing is claimed.
  Owner access/restart of Streamlit remains necessary for live engine verification.

## Deployment checkpoint — 6 October, 20:08 UTC

- Re-read persisted production and verified the live public index: 905/905 rows
  matched, including exact source-brand facts. North West: 138 source lots parsed,
  28 commercial/mixed-use candidates, four publication exclusions, 24 published
  and 24 live. This is the pre-refresh snapshot, not the new collector output.
- Found and fixed the remaining regional-identity loss in the EARLY production
  finalizer, before publication deduplication. Commit `8524cdc55d89` unions source
  brands when an identical online URL/date is shared. The actual-finalizer
  regression passes; this needs a fresh scan because old deduplicated rows have
  already lost those identities. Do not repeat the earlier consumer-only fix.
- Production run `37521620496` is collecting the three new current catalogues
  (Sutton Kersh, Edward Mellor, Under The Hammer). Run `37522592334` is queued with
  the early-finalizer correction. Allow these to finish; do not launch overlapping
  scans. The 33 locally collected qualifying rows are NOT yet claimed live.
- Pages runs `37521620921`, `37522273225` and `37522592130` succeeded. Legal Pack
  Engine Tests `37522273286` succeeded. No new historical sources were started.
- Streamlit owner profile shows Sign in, with no authenticated management session.
  Automatic browser approval review rejected opening its authentication origin
  because the user previously required a stop-and-ask at sign-in. Ask for owner
  sign-in before trying that flow again; do not bypass this refusal. The old
  analysis heading is still live. The new engine fingerprint is on main, not
  verified deployed in Streamlit.
- Phone check: 390px frame, 130px upcoming rail, document width 390px, and normal
  scrolling verified. Desktop rail approximately 86px. Screenshots were preserved.

# Operational checkpoint — 5 October 2026

## 6 October evening — owner access and live analysis recovery

- User authenticated Streamlit through GitHub and explicitly requested the session
  be retained. Owner dashboard confirmed `garethburke5`, `main`, `app.py`. Rebooted
  the existing app; its repository clone took approximately nine minutes. The
  live screen now shows Acquisition Intelligence 3, not the legacy v2 interface.
- Ran a clearly labelled synthetic ZIP through the LIVE app: three nested text
  documents were processed; seller contribution £2,750 + VAT was calculated as
  £3,300 with source filename. This is not a reprocessing of the Newbury pack.
- End-to-end ingestion tests exposed narrow ordinary-wording gaps in seller fees,
  deposit and completion clauses. Fixed these without treating default-only costs
  as unconditional fees, inventing VAT commentary, or using historic rent as GIY.
- Live visual review found CSS overriding the full-review panel's text contrast.
  Fixed panel/primary-button contrast, duplicate Deep Dive presentation and repeated
  completion wording. Multiple lease documents no longer collapse into one header
  term. Combined relevant regression suite: 24 passed.
- Both pending production scans succeeded. Fresh persisted/live verification:
  913/913 rows; Sutton Kersh five and Edward Mellor three are customer-findable;
  North West 24, Midlands eight, Coventry two, Hull one are represented live.
- Under The Hammer: GitHub Actions received HTTP 403 (health degraded). The same
  public API remains accessible from this operator workspace. Freshly traversed
  440/440 records with the existing collector; 25 qualifying current lots (13
  commercial, 12 mixed-use). Source-only snapshot integration passed the UNCHANGED
  full publication gate at 938 rows. Published in `63646073def8f57181d762298281f2720a85f4d5`;
  Pages run `37534930968` succeeded, including source-to-live verification: 938/938.
  Customer filter independently shows all 25 lots, primary photographs display,
  and 18 Northgate's detail page shows source evidence, current rent and GIY.
  Fresh public 390px viewport has document width 390px with no horizontal overflow.
  Capture runtime and original scheduled error are retained in source health.
- Fixed last-known-good retention for explicit DEGRADED discovery outages as well
  as FAILED outages. Past lots remain excluded; unavailable catalogues are unknown,
  not falsely absent. No new historical auctioneer expansion was started.
- Live account page still explicitly awaits account sign-in and email activation.
  These, checkout and paid-report access remain commercial-release blockers; the
  visible plans/dashboard are not evidence that the private services are active.
- Final live analysis check: reboot completed at 21:47 UTC; engine `439af9d32cff`
  matches the deployed source. A fresh three-document synthetic ZIP produced the
  correct £3,300 cost, one Deep Dive, readable full-review panel and a downloadable
  HTML carrying the same engine ID. This verifies deployment/presentation, NOT the
  substantive Newbury report. The phone form renders at 390px without overflow;
  phone-frame file-chooser automation timed out, so mobile upload is not signed off.
- Retain authenticated Streamlit owner session. No new credentials were created.
  Next: remaining current gaps (Wilsons/iamsold/Cheffins and registry assessments),
  sustainable scheduled Under The Hammer collection (Actions 403 persists), source
  health, real-pack quality, then account/billing/report-access activation.

## Earlier 5 October checkpoint

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
- Final combined regression suite: 669 passed plus eight subtests. The exact Pages
  publication gate passed 86 tests. Full export: 1,552 pages.
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
- Final deployment `6fbeebc8`, Pages run `37339282127`, succeeded. Its stronger
  fact verification matched all 782 published/live property IDs and guide/yield/
  status fields. Live HTTP property checks confirm Maybole and Alloway Street are
  Vacant with current rent and GIY not stated; Crouch Hill shows £111,244 rent,
  7.1% GIY, £43,000 commercial + £68,244 residential components. Target input is
  blank and retained. These are HTTP/data checks, not new browser visual checks.
- At handoff, refreshed regional collection run `37336848982` remains running.
  Do not count recovered source stock until its snapshot, logs and live deployment
  are checked. No new historical harvest operation was started by this tranche.
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


## Launch continuation — 7 October 2026

Launch remains blocked; do not enable billing or describe paid monitoring as operational.

- Recovered prior implementation/handover and checked the live Pages account boundary. Supabase, a persistent private API host, Stripe prices/webhooks and SMTP are still unconfigured in the accessible environment. Existing private journeys pass mocked provider tests; no real provider acceptance has occurred.
- Investigated failed production scan 37627992526. Its 13:48 UTC candidate had 1,062 rows; classification contamination caused two rich-detail thresholds to fail. Fixed agency-credit and unpunctuated Location scoping, preserved real salon/industrial/yard evidence, excluded unproved land parcels. The corrected candidate has 1,057 rows and passes the existing publication gate without reduced thresholds. A fresh scan will be triggered by the scan-workflow change.
- Added hourly freshness workflow (14-hour maximum, two six-hour collection intervals plus grace) and degraded unexplained zero publication where source lots exist but catalogue currency is unknown. GitHub Actions failures are visible alarms; no external notification delivery is claimed.
- Recovered the complete 38-document Newbury pack and the exact amended special conditions (hash 46616fa2abf54f3b4b334eb66ce259451dcb99e659ecf198e04faaf9422401b3). Real processing: 540 pages, 57 OCR pages, one unread page (asbestos report page 19). Private PDFs/results stay outside this public repository.
- Corrected document roles (rent-authority/ID/common-condition documents are not occupational leases; freehold register, rent schedule and environmental report identified), lease party extraction, LLP proprietor, qualified title exclusion, fee-version conflicts and pennies. Review models 2,400 seller contribution + 1,800 auctioneer fee = 4,200 fixed charges; 100 capped disbursements and 372.83 works balance remain separate and qualified. Default notice charge preserves numeric/written inconsistency rather than adding it as fixed.
- Visually checked amended conditions page 4 and Arcade lease page 7: the latter contains overlapping edited date text, so final operative-date confirmation remains necessary. Complete pack commercial acceptance is still OPEN: reconcile income components, ground rents, breaks/repair terms, CPSE/search findings and unread/plan evidence before selling the review.
- Corrected mixed shop/ground-rent investment board labelling.
- Validation before publication: 807 tests + 8 subtests passed, followed by focused coverage for the contingent default-charge finding. Next: verify deployment/fresh scan, then configure providers and run test-mode registration → saves → membership → report purchase → verified webhook → owner-only report revisit, including mobile. Scheduled monitoring/email delivery remains unbuilt/unactivated; existing watches run on account return.
