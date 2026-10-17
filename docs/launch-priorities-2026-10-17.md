# Auction Geek launch acceptance — 17 October 2026

This supersedes the 12 October status table. It separates implemented controls, deployment evidence and outstanding real customer acceptance. Live billing and paid report sales remain closed.

| Priority | Status | Verified evidence and remaining gate |
| --- | --- | --- |
| 1. Backend deployment | PARTIAL | Startup/port problem fixed, account API ready, automatic code deployments observed. Session-revocation release `1b505005` is live on Render and Cloudflare; readiness independently matched. Interrupted monitoring recovered through the existing signed scheduler at 19:26 UTC, completing in 22 seconds with HTTP 200. Free-instance wake-up behaviour and complete customer acceptance remain open. |
| 2. Registration/accounts | PARTIAL | Owner has confirmed password reset and saved-property return persistence. Account navigation and forms implemented. Signed-token revocation protection is deployed and passed local/PostgreSQL checks; real browser sign-out/return acceptance and production-email verification remain open. |
| 3. Proprietor access | PARTIAL | Owner allow-list configured and owner reports seeing the section. Full customer-tier preview and latest owner-session acceptance remain to record. |
| 4. Stripe/memberships | PARTIAL | Sandbox subscriptions, renewal, downgrade, cancellation and duplicate webhook handling have recorded deployed evidence. Refund/credit safeguards have tests and prior reconciliation. Real failed-renewal/recovery and the complete report purchase journey remain open. Current connector exposes the sandbox but not test-clock advance/payment-method attachment. No live transactions were attempted. |
| 5. Report quality | BLOCKED | Existing optional-pack engine and customer journey reused. Live readiness reports no analysis provider configured. Need secure provider configuration, fresh real reports with and without packs, Newbury EPC/listed/lease checks and approval of actual output. |
| 6. Report cost/access | PARTIAL | Usage accounting, ownership, post-membership entitlement and interrupted-job controls exist and have regression evidence. No representative live AI cost/margin measurement. Actual generated-report download/logout/return and provisional 30-day update-policy acceptance remain open. |
| 7. Watch/alerts | PARTIAL | Scheduled monitoring has signed production execution evidence. Daily opt-in delivery code and restricted recipient lookup deployed; sending remains off. Need verified Resend sender, sending key, signed receipt webhook, owned-inbox delivery/unsubscribe test and approved retention. Authentication email does not prove alert delivery. |
| 8. Data reliability | PARTIAL | Permanent-history banking is succeeding; the old timeout is not a current failure. Loveitts 22/22 current cards matched to existing regional feed. Cheffins timed collector exists; rostrum and other source coverage still need sign-off. Fox & Sons and Connells relationships assessed below without claiming full coverage. |
| 9. Safeguards/acceptance | PARTIAL | Interrupted-job fencing/recovery and disposable database restore checks passed. Restore fixture includes Auth identity, report ownership, credits and email opt-out. No production backup/download/restore proof; retention/deletion and complete desktop/mobile paid journey still open. |

## Additional current-source evidence

Fox & Sons: https://www.foxandsonsauctions.co.uk/Current_Auction.html invites entries for 17 November. Its homepage at https://www.foxandsonsauctions.co.uk/ contains 22 results from 15 October, all linking to exact Barnard Marcus lot URLs. These links include unsold, sold and withdrawn lots. This supports reuse of the canonical feed, not discarding those states or creating a duplicate collector. The existing Barnard Marcus health snapshot is degraded (16 future pages discovered, 15 inspected, one failed, no qualifying current published rows). Post-auction availability and brand-level inventory reconciliation remain unresolved. Fox & Sons also markets modern-method auctions through iamsold; do not conflate its two channels.

Connells: https://www.connells.co.uk/services/modern-method-of-auction explicitly identifies iamsold as its provider. The existing iamsold collector is the first place to reconcile those lots. No count equivalence or complete ingestion is inferred from that relationship, nor is it a statement about every traditional Connells Group auction.

Loveitts evidence is in `loveitts-reconciliation-2026-10-17.md`. Hollis Morgan's site returned HTTP 429 during assessment; it was not bypassed, and stale search snippets were not used as current inventory. Other recorded gaps and shared Auction House feeds remain open. Withdrawn lots must remain findable with accurate availability labels.

## Deferred enhancements

The free commercial buyer checklist is scoped in `commercial-buyer-checklist-scope.md`; no new public feature has been built. Historical expansion, deeper marketing/tenant history, wider comparisons, sponsored listings and professional-service activation remain behind launch acceptance.

## Next external configuration needed

Use existing provider accounts and enter secrets directly into Render's environment settings, never public builds or chat. The existing report provider requires its API key and model configuration; the daily alerts service requires its verified Resend sender/key/webhook settings. Keep `BILLING_LIVE=false` and alert sending disabled until the corresponding acceptance steps are complete. Production backup recovery needs a verified owner-controlled export/restore method; a healthy database alone is not backup evidence.
