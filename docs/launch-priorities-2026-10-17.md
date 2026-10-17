# Auction Geek launch acceptance — 17 October 2026

This supersedes the 12 October status table. It separates implemented controls, deployment evidence and outstanding real customer acceptance. Live billing and paid report sales remain closed.

| Priority | Status | Verified evidence and remaining gate |
| --- | --- | --- |
| 1. Backend deployment | PARTIAL | Startup/port problem fixed; the later 16 GB temporary-build-storage eviction is also corrected. Clean-cache build `dep-db9u15qog99s7390vim0` demonstrably ran the guarded cleanup script and became live at 21:01:38 UTC; the next automatic update succeeded at 21:04:23. Account API access controls and website-origin preflight passed. Details: `render-build-storage-2026-10-17.md`. Free-instance wake-up behaviour and complete customer acceptance remain open. |
| 2. Registration/accounts | PARTIAL | Owner has confirmed password reset and saved-property return persistence. Account navigation and forms implemented. Signed-token revocation protection is deployed and passed local/PostgreSQL checks; real browser sign-out/return acceptance and production-email verification remain open. |
| 3. Proprietor access | PARTIAL | Owner allow-list configured and owner reports seeing the section. Full customer-tier preview and latest owner-session acceptance remain to record. |
| 4. Stripe/memberships | PARTIAL | Sandbox subscriptions, renewal, downgrade, cancellation and duplicate webhook handling have recorded deployed evidence. Refund/credit safeguards have tests and prior reconciliation. Real failed-renewal/recovery and the complete report purchase journey remain open. Current connector exposes the sandbox but not test-clock advance/payment-method attachment. No live transactions were attempted. |
| 5. Report quality | BLOCKED | Existing optional-pack engine and customer journey reused. Live readiness reports no analysis provider configured. Need secure provider configuration, fresh real reports with and without packs, Newbury EPC/listed/lease checks and approval of actual output. |
| 6. Report cost/access | PARTIAL | Usage accounting, ownership, post-membership entitlement and interrupted-job controls exist and have regression evidence. No representative live AI cost/margin measurement. Actual generated-report download/logout/return and provisional 30-day update-policy acceptance remain open. |
| 7. Watch/alerts | PARTIAL | Scheduled monitoring has signed production execution evidence. Daily opt-in delivery code and restricted recipient lookup deployed; sending remains off. Need verified Resend sender, sending key, signed receipt webhook, owned-inbox delivery/unsubscribe test and approved retention. Authentication email does not prove alert delivery. |
| 8. Data reliability | PARTIAL | Permanent-history banking is succeeding; the old timeout is not a current failure. Loveitts 22/22 current cards matched to existing regional feed. Cheffins timed collector exists; rostrum and other source coverage still need sign-off. Barnard Marcus latest-result discovery and availability checks corrected. McHugh template repair reads 208/208 current pages without detail failures and yields ten qualifying candidates; production publication is queued. See source-specific reconciliation records. Under The Hammer feed access and full source sign-off remain open. |
| 9. Safeguards/acceptance | PARTIAL | Interrupted-job fencing/recovery and disposable database restore checks passed. Restore fixture includes Auth identity, report ownership, credits and email opt-out. No production backup/download/restore proof; retention/deletion and complete desktop/mobile paid journey still open. Critical public SEO checks and two targeted corrections are recorded in `organic-launch-checkpoint-2026-10-17.md`; webmaster verification and indexing evidence remain open. |

## Latest verification additions

The 21:00–21:04 UTC deployment checks and guarded build cleanup are recorded in `render-build-storage-2026-10-17.md`. Production Supabase permissions were checked read-only: private tables and views are unavailable to browser roles, all private tables have RLS enabled, and the API role cannot bypass RLS. `database-launch-security-2026-10-17.md` records the remaining leaked-password-protection warning and the limits of this check. Authenticated isolation and production restore acceptance remain open.

Fresh McHugh reconciliation is recorded in `mchugh-launch-reconciliation-2026-10-17.md`: 208 details read, zero failures, ten qualifying candidates, with hosted publication pending behind the active scan. The 20:44 production snapshot now reports Barnard Marcus available inventory as 135 advertised/135 observed, resolving the earlier 137/135 discrepancy below; two missing-detail pages still prevent complete source sign-off. No extra Stripe transaction or live email was sent in this batch. Failed-renewal/recovery remains open because the available connector cannot advance the test clock and the Stripe browser is signed out.

The scheduled monitor completed an unattended run from 20:11:00 to 20:12:10 UTC on 17 October; this is separate from the earlier manually requested recovery. No alert emails were enabled or sent.

Barnard Marcus/Fox reconciliation checked 363 detail URLs and retained 11 qualifying commercial candidates after the publication gate. Two detail pages lack particulars, and the available feed returns 135 of its advertised 137 cards. Health stays degraded. All 22 Fox links match canonical discovery; one mixed-use lot has conflicting availability evidence and full brand coverage is not signed off. Production publication must still complete before these newly collected rows are described as live.

## Additional current-source evidence (initial assessment)

Fox & Sons: https://www.foxandsonsauctions.co.uk/Current_Auction.html invites entries for 17 November. Its homepage at https://www.foxandsonsauctions.co.uk/ contains 22 results from 15 October, all linking to exact Barnard Marcus lot URLs. These links include unsold, sold and withdrawn lots. This supports reuse of the canonical feed, not discarding those states or creating a duplicate collector. The existing Barnard Marcus health snapshot is degraded (16 future pages discovered, 15 inspected, one failed, no qualifying current published rows). Post-auction availability and brand-level inventory reconciliation remain unresolved. Fox & Sons also markets modern-method auctions through iamsold; do not conflate its two channels.

Connells: https://www.connells.co.uk/services/modern-method-of-auction explicitly identifies iamsold as its provider. The existing iamsold collector is the first place to reconcile those lots. No count equivalence or complete ingestion is inferred from that relationship, nor is it a statement about every traditional Connells Group auction.

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

Use existing provider accounts and enter secrets directly into Render's environment settings, never public builds or chat. The existing report provider requires its API key and model configuration; the daily alerts service requires its verified Resend sender/key/webhook settings. Keep `BILLING_LIVE=false` and alert sending disabled until the corresponding acceptance steps are complete. Production backup recovery needs a verified owner-controlled export/restore method; a healthy database alone is not backup evidence.
