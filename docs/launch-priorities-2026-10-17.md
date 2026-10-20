# Auction Geek consolidated launch brief — updated 18 October 2026

Current whole-project backlog: [20 October master delivery backlog](master-backlog-2026-10-20.md).
The owner has explicitly resumed historical collection alongside report work.
The older archive deferral below is superseded; dated acceptance evidence remains
limited to what was actually checked. Paid report approval remains closed.

This supersedes the 12 October status table. It separates implemented controls, deployment evidence and outstanding real customer acceptance. Live billing and paid report sales remain closed. The report-product decision below is updated on 18 October; other dated checkpoints retain their recorded scope and are not newly certified by this update.

| Priority | Status | Verified evidence and remaining gate |
| --- | --- | --- |
| 1. Backend deployment | PARTIAL | Startup/port problem fixed; the later 16 GB temporary-build-storage eviction is also corrected. Clean-cache build `dep-db9u15qog99s7390vim0` demonstrably ran the guarded cleanup script and became live at 21:01:38 UTC; the next automatic update succeeded at 21:04:23. Account API access controls and website-origin preflight passed. Details: `render-build-storage-2026-10-17.md`. Free-instance wake-up behaviour and complete customer acceptance remain open. |
| 2. Registration/accounts | PARTIAL | Owner has confirmed password reset and saved-property return persistence. Account navigation and forms implemented. Signed-token revocation protection is deployed and passed local/PostgreSQL checks; real browser sign-out/return acceptance and production-email verification remain open. |
| 3. Proprietor access | PARTIAL | Owner allow-list configured and owner reports seeing the section. Full customer-tier preview and latest owner-session acceptance remain to record. |
| 4. Stripe/memberships | PARTIAL | Sandbox subscriptions, renewal, downgrade, cancellation and duplicate webhook handling have recorded deployed evidence. Refund/credit safeguards have tests and prior reconciliation. Real failed-renewal/recovery and the complete report purchase journey remain open. Current connector exposes the sandbox but not test-clock advance/payment-method attachment. No live transactions were attempted. |
| 5. Report quality — FIRST PRIORITY | REJECTED / NOT READY FOR SALE | Owner rejected both 18 October Newbury specimens: with-pack 5/10, no-pack 3/10 for usefulness/presentation. The £19 price is retained. The no-pack route should become a free Snapshot; insufficient-evidence outputs must carry no charge. Shared design, independent commercial analysis, property-specific costs, meaningful visuals and robust editorial QC must pass the diverse-case matrix in `report-product-rejection-2026-10-18.md`. API credit is not a dependency for formulation or offline validation. These product/routing requirements are not claimed implemented. |
| 6. Report cost/access | PARTIAL | Usage accounting, ownership, post-membership entitlement and interrupted-job controls exist and have regression evidence. No representative live AI cost/margin measurement. Actual generated-report download/logout/return and provisional 30-day update-policy acceptance remain open. |
| 7. Watch/alerts | PARTIAL | Scheduled monitoring has signed production execution evidence. Daily opt-in delivery code and restricted recipient lookup deployed; sending remains off. Need verified Resend sender, sending key, signed receipt webhook, owned-inbox delivery/unsubscribe test and approved retention. Authentication email does not prove alert delivery. |
| 8. Data reliability | PARTIAL | Permanent-history banking is succeeding; the old timeout is not a current failure. Loveitts 22/22 current cards matched to existing regional feed. Cheffins now combines its timed feed with the linked current rostrum catalogue using the existing parser: fresh checks read 19 timed and 24 rostrum cards; hosted acceptance is pending. Barnard Marcus latest-result discovery and availability checks corrected. McHugh's repaired collector has completed hosted publication: 208/208 pages read and ten current commercial/mixed-use rows in the 21:38 UTC snapshot; Cloudflare publication and all ten rows in the live index are verified. Under The Hammer feed access and wider source sign-off remain open. |
| 9. Safeguards/acceptance | PARTIAL | Interrupted-job fencing/recovery and disposable database restore checks passed. Restore fixture includes Auth identity, report ownership, credits and email opt-out. No production backup/download/restore proof; retention/deletion and complete desktop/mobile paid journey still open. Critical public SEO checks and two targeted corrections are recorded in `organic-launch-checkpoint-2026-10-17.md`; webmaster verification and indexing evidence remain open. |

## Immediate priority override — report quality

The current feature-wide feedback audit is
[`report-feedback-status-2026-10-18.md`](report-feedback-status-2026-10-18.md).
It distinguishes shared implementation from edited specimens and unfinished
customer behaviour, and reconciles the owner's later corrections. Do not count
a report rewrite, additional test case or deployment as product acceptance.

The owner made Property Investment Reports the immediate priority on 17 October and rejected both subsequent Newbury specimens on 18 October. Defer further source expansion and analytics-dashboard development while completing the report product. Continue existing collection and essential reliability work. All other launch priorities remain in scope.

**Binding report brief:** [`report-product-rejection-2026-10-18.md`](report-product-rejection-2026-10-18.md). The standard is also reflected in [`investment-report-standard.md`](investment-report-standard.md). The 17 October report checkpoint remains historical engineering evidence, not the current acceptance specification.

Keep the Full Investment Report at **£19** and leave paid approval off. Develop the public-information/no-pack output as a useful **free Property Snapshot**. An insufficient-evidence outcome must explain the gaps and result in **no charge or consumed credit**. Pack presence is not proof that a report is worth buying. Charging, refund and sufficiency behaviours require implementation and customer verification before they are claimed complete.

The next submission must contain a substantially better three-to-five-page main report design, useful independent commercial analysis and quality controls demonstrated on at least four distinct properties, plus a no-pack control and incomplete-evidence variant. At least one case must be unseen after the template/rules are fixed, and accepted full reports must cover at least three materially different property types. Retain rejected cases instead of cherry-picking successful reports. Include actual PDFs, source/comparable ledgers, financial workings, chart/QC checks and a completed pass/fail record. An isolated Newbury rewrite or passing test count does not meet this milestone.

Use retained evidence and offline fixtures for design, financial logic, editorial safeguards and report review now. Manual curation must be disclosed. API credit is relevant to later production-provider validation, not a prerequisite for mastering the report. After the product passes, prove automated equivalence, complete cost accounting and the purchase/credit/download/logout/return/post-membership journey. Owner approval of the actual product is required before paid reporting opens.

### Preserved launch scope

The numbered priorities above remain active: accounts and proprietor access; membership/payment lifecycle; report ownership, cost and continuing access; alerts and unsubscribe; source reconciliation and accurate availability; backup/restore, retention and desktop/mobile acceptance. The £0 paid-advertising constraint and organic SEO requirements below also remain unchanged.

Owner-only statistics remain scoped and **pending activation/verification**: Cloudflare Web Analytics for visits, page views, referrals and devices; Google Search Console for search/indexing; Bing Webmaster Tools and available Google/Bing link reports for discovered backlinks/referring sites. Counts represent each provider's discovery, not every link online. Reuse free dashboards first. See `organic-launch-checkpoint-2026-10-17.md`; do not describe an analytics dashboard as live or use missing data as zero.

## Latest verification additions

18 October implementation: shared renderer, evidence safeguards and free Snapshot downloads rebuilt; eight review documents across seven properties produced. See `report-rebuild-validation-2026-10-18.md` for actual results and remaining gates. This is not paid-product approval.


Cheffins commit `ef0a64302c882a016115fcadff56a1f51c6d0f12` adds current-rostrum integration, evidenced medical/garage classification fixes and safe handling of component floor areas and partial occupation. The fresh dual-feed check and 884 passing collector tests plus 19 subtests are recorded in `cheffins-rostrum-launch-checkpoint-2026-10-17.md`. Render deployment `dep-db9umfu90tus73c9vlfg` became live at 21:45:07 UTC. Production run `39071920684` is collecting; new Cheffins rostrum records are not yet accepted as publicly deployed.

McHugh production run `39069165519` completed successfully and committed snapshot `efcc005674b86706d1c2739d08c4ee23aca00dd9`, generated at 21:38:33 UTC. All ten qualifying current McHugh rows are present in that snapshot, with zero detail failures. The Cloudflare Workers build subsequently succeeded. The live workspace index matches the 21:38:33 snapshot and contains all ten current rows plus six retained older McHugh records (16 total); the new Exeter page returned HTTP 200 with the expected address and original auctioneer link.

The 21:00–21:04 UTC deployment checks and guarded build cleanup are recorded in `render-build-storage-2026-10-17.md`. Production Supabase permissions were checked read-only: private tables and views are unavailable to browser roles, all private tables have RLS enabled, and the API role cannot bypass RLS. `database-launch-security-2026-10-17.md` records the remaining leaked-password-protection warning and the limits of this check. Authenticated isolation and production restore acceptance remain open.

Fresh McHugh reconciliation is recorded in `mchugh-launch-reconciliation-2026-10-17.md`: 208 details read, zero failures, ten qualifying candidates, with hosted and public publication subsequently verified above. The 20:44 production snapshot now reports Barnard Marcus available inventory as 135 advertised/135 observed, resolving the earlier 137/135 discrepancy below; two missing-detail pages still prevent complete source sign-off. No extra Stripe transaction or live email was sent in this batch. Failed-renewal/recovery remains open because the available connector cannot advance the test clock and the Stripe browser is signed out.

The scheduled monitor completed an unattended run from 20:11:00 to 20:12:10 UTC on 17 October; this is separate from the earlier manually requested recovery. No alert emails were enabled or sent.

Barnard Marcus/Fox reconciliation checked 363 detail URLs and retained 11 qualifying commercial candidates after the publication gate. Two detail pages lack particulars, and the available feed returns 135 of its advertised 137 cards. Health stays degraded. All 22 Fox links match canonical discovery; one mixed-use lot has conflicting availability evidence and full brand coverage is not signed off. Production publication must still complete before these newly collected rows are described as live.

## Additional current-source evidence (initial assessment)

Fox & Sons: https://www.foxandsonsauctions.co.uk/Current_Auction.html invites entries for 17 November. Its homepage at https://www.foxandsonsauctions.co.uk/ contains 22 results from 15 October, all linking to exact Barnard Marcus lot URLs. These links include unsold, sold and withdrawn lots. This supports reuse of the canonical feed, not discarding those states or creating a duplicate collector. The existing Barnard Marcus health snapshot is degraded (16 future pages discovered, 15 inspected, one failed, no qualifying current published rows). Post-auction availability and brand-level inventory reconciliation remain unresolved. Fox & Sons also markets modern-method auctions through iamsold; do not conflate its two channels.

Connells: https://www.connells.co.uk/services/modern-method-of-auction explicitly identifies iamsold as its provider. The existing iamsold collector is the first place to reconcile those lots. No count equivalence or complete ingestion is inferred from that relationship, nor is it a statement about every traditional Connells Group auction.

Commercial.Auction and Resi.Auction currently serve the same Probate.Auction public content and links. This establishes a shared public journey only; catalogue counts, identities and ongoing ingestion remain unverified. SW Property Auctions identifies itself as Sanderson Weatherall, but its catalogue returned HTTP 403 during direct inspection; no bypass was attempted. Aberdein Considine remains unverified. These are open reconciliation items, not completed collectors.

Loveitts evidence is in `loveitts-reconciliation-2026-10-17.md`. Hollis Morgan's site returned HTTP 429 during assessment; it was not bypassed, and stale search snippets were not used as current inventory. Other recorded gaps and shared Auction House feeds remain open. Withdrawn lots must remain findable with accurate availability labels.

## Ongoing organic growth requirement — agreed 17 October 2026

Customer acquisition has a **£0 paid-advertising budget**. Prioritise free organic discovery through Google, Bing, relevant AI search services and legitimate referrals, especially for UK commercial-property investors. This does not change the paid membership/report offering. No paid campaigns, paid backlink schemes or new growth subscriptions are authorised by this directive.

### Launch acceptance within existing priorities 8 and 9

Inspect and reuse the current collection, templates and publishing pipeline. Verify deployed search-friendly permanent URLs, meaningful titles/meta descriptions, canonical handling, XML sitemaps, appropriate accurate structured data, internal discovery links, crawl/index controls and mobile performance. Preserve existing URL equity; use redirects where a necessary URL change occurs.

Every worthwhile property should retain a useful permanent public page after the auction, with dated evidence and accurate sold, unsold or withdrawn status. Distinguish historic records from currently available stock. Automatically expose qualifying new property, auctioneer and useful location pages through existing publishing, internal links and sitemaps. Avoid duplicate shared-feed pages, empty location combinations, thin repetitive pages and fabricated information. Private accounts, packs and purchased reports must remain protected; SEO never bypasses access controls.

Establish/verify Google Search Console and Bing Webmaster Tools ownership, submit the canonical sitemap and record indexing/coverage evidence when access permits. Mark this as pending until verified; no search ranking or indexing outcome is promised. Include organic measurement for impressions, clicks, relevant query positions and privacy-respecting visitor/referral data using existing or free tools.

### After essential launch functionality

Build on original, attributable historical auction records, previous marketing appearances, price changes, tenant evidence and useful investment analysis. Reuse the auction calendar and existing calculators before expanding free resources, including the already-scoped commercial buyer checklist, market statistics and focused guides. New location/content pages require genuine distinct value.

Make public original evidence understandable through readable HTML, clear entities, source attribution and dates for conventional and AI search discovery. Respect crawler controls and customer privacy; do not expose private report content.

Assess legitimate free promotion through relevant industry/resource directories, useful data citations, editorial contributions, professional communities and referral relationships. No automated spam or unsolicited outreach is authorised; sending messages still requires explicit authorisation.

This is an ongoing constraint on existing launch work, not a separate immediate workstream. Broader content development, historical expansion and promotion remain behind report quality/cost, accounts, payments, alerts and recovery acceptance. Recheck current official search-engine guidance when implementing; this roadmap records requirements, not a completed SEO audit.

## Deferred enhancements

The free commercial buyer checklist is scoped in `commercial-buyer-checklist-scope.md`; no new public feature has been built. Historical expansion, deeper marketing/tenant history, wider comparisons, sponsored listings and professional-service activation remain behind launch acceptance.

## Next external configuration needed

Use existing provider accounts and enter secrets directly into Render's environment settings, never public builds or chat. The old missing-report-key note is superseded as an immediate work dependency: report formulation and offline quality acceptance proceed without provider credit. Production provider availability, automated output and complete cost accounting still require separate verification before release. The daily alerts service requires its verified Resend sender/key/webhook settings. Keep `BILLING_LIVE=false`, the paid-report approval gate off and alert sending disabled until their corresponding acceptance steps are complete. Production backup recovery needs a verified owner-controlled export/restore method; a healthy database alone is not backup evidence.

### Editorial rejection follow-through, 18 October 2026

The next report build adds separate investment interpretation and plain-English editing, two primary achieved Newbury comparisons, and nine revised documents across eight properties. See `docs/report-editorial-rebuild-2026-10-18.md` for the changes, evidence and explicit limits. Paid-report approval remains closed. Original launch priorities remain in place; this work does not approve paid reports, live billing, alert delivery or owner analytics activation.
