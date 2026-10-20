# Auction Geek master delivery backlog — 20 October 2026

The owner has instructed continuous progress across the full programme, with
substantial completion sought over the next few days. This supersedes the earlier
pause on discretionary historical collection. Report product quality remains
critical; nationwide collection and permanent history are core products too.
Do not report all jobs complete from passing software tests or a few specimen PDFs.

## Active delivery batch

| Work | Evidence / remaining acceptance |
|---|---|
| Return credits for rejected reports | Shared transactional implementation published in `258c628`; replacement survives membership expiry; original funding revocation applies. Hosted PostgreSQL checks passed. Actual customer journey still open. |
| Refund rejected one-off reports | Durable outbox, current-payment verification, duplicate prevention and scheduled retry implemented. Real Stripe sandbox refund acceptance remains open. Paid sales stay closed. |
| Exhausted processing retries | Third failed customer attempt enters settlement; owner validation and included updates cannot create compensation for an unpaid job. |
| Restore current scanning | Latest scheduled runs 39334268851 and 39371647710 stopped at the Savills Hanover tenure regression, before collection. Parser correction published in `514d71d`; 1,039 collector tests plus 22 subtests passed. Production run `39402418825` passed regression checks and reached collection; fresh publication remains pending. |
| Resume historical collection | Existing workflow was explicitly disabled on 8 October. Resumed with two rotating ten-minute tasks per scheduled run and persisted outcomes. Runs `39402418694` and `39403320245` completed and committed checkpoints `91b1a724` and `5ff31149`. Neither batch added appearances or addresses; total remains 270,629. The six-hour schedule is active; this is automated collection, not a promise of an agent working between conversations. |
| Publish the actual rebuilt historical database | Existing compressed database is 99,928,416 bytes; old workflow could commit newer counts while leaving the older database above its 99 MB staging threshold. Verified multipart delivery is implemented and the site reader prefers it. The rebuilt 144,216,157-byte compressed database was checkpointed successfully in five parts; legacy storage is retained. |
| Measured coverage audit | `coverage-audit-2026-10-20.json` records the current retained source evidence. A reusable audit command is included. No national denominator has been established. |

## Comprehensive coverage and historical database

| ID | Job | Completion evidence required |
|---|---|---|
| D1 | Maintain the UK auctioneer/brand/branch register | Document source discovery, current status, feed relationships and missing houses. Existing registry is not a complete national census. |
| D2 | Capture every current UK auction lot | Advertised, inspected, banked and publicly displayed counts reconciled per auction; explain each exclusion/failure. |
| D3 | Preserve all property types | Commercial focus can remain in presentation, but residential/land records must be retained for the nationwide database. Current commercial collectors often discard residential results after inspection. |
| D4 | Complete historical collection | Bank individual lot appearances, not catalogue shells. Resume Savills back to 2013 and other recoverable UK sources; retain partial records honestly. |
| D5 | Repair incomplete catalogues and addresses | Latest counted archive: 270,629 appearances, 260,253 with addresses, 10,376 partial records; 618 incomplete/unreconciled catalogues and 69 fetch/parse failures, dated 8 October. These are a baseline, not newly collected totals. |
| D6 | Resolve repeat properties across auctioneers | Conservative building/unit matching; no merging neighbours or separate flats. Retain provenance and uncertain matches. |
| D7 | Complete property timelines and comparisons | Dated guides, asking prices, rent changes, results and reappearances visible to customers and available to reports. |
| D8 | Preserve outcomes/permanent pages | Sold, sold prior, unsold, withdrawn and reoffered states updated without losing earlier evidence. |
| D9 | Owner coverage dashboard | Owner-only API and expandable workspace panel now implemented with catalogue timestamps, source counts/statuses, historical totals and gaps. Hosted Chromium tests passed, including mobile overflow and sign-out clearance; API deployed on Render. The main-domain frontend still awaited Cloudflare publication at the last check. Actual owner-session acceptance remains open because the verification browser is signed out; national denominator remains unknown. |
| D10 | Resolve named source gaps | Bond Wolfe detail failures; Barnard Marcus incomplete particulars; Under The Hammer access; Cheffins final reconciliation; Loveitts/Fox/Connells shared-feed attribution; remaining registry assessments. |
| D11 | Search and listing accuracy | Tenant/business-name search; correct classification, unit areas, current rent, yield filters, original hero images, duplicate prevention and clear fees. Recheck old snags before claiming closed. |

## Reports and snapshots

| ID | Job | Completion evidence required |
|---|---|---|
| R1 | Excellent £19 automated full report | Natural professional prose, clear introduction/unit income breakdown, useful independent analysis, proportional findings and end references; actual untouched outputs accepted. |
| R2 | Reliable original-pack interpretation | Tenant/security, title chain, access, renewal protection, unit-specific EPCs, asbestos evidence, repair recovery and visual plan interpretation on unfamiliar properties. |
| R3 | Financial and market analysis | Sustainable rent, relevant achieved comparables, acquisition/transaction costs, property-specific liabilities, vacancy/reletting and exit scenarios with supported assumptions. |
| R4 | Diverse acceptance set | At least four cases, at least three materially different full-report property types, an untouched holdout, no-pack control and incomplete-evidence case. Preserve failures/manual inputs. |
| R5 | Deterministic free snapshot | Implemented/live from captured catalogue data, no per-view AI/research/PDF-service calls. Keep improving useful explanations and completeness without importing private packs. |
| R6 | Convenient supporting evidence | End references and retained extracts implemented; original PDF page viewing and complete customer permissions/access acceptance remain open. |
| R7 | Report ownership and delivery | Purchase/redemption, generation, downloads, logout/return, expiry, rejection/refund and included pack-update journeys verified. |
| R8 | Measured report economics | Actual provider usage, retries/failures, complete cost ledger and margin at £19. Credit exhaustion blocks production-provider tests, not offline development. |
| R9 | Final approval before paid release | Owner reviews the demonstrated automated product. No billing configuration or passing tests can open the quality gate implicitly. |

## Accounts, launch and business operations

| ID | Job | Remaining work |
|---|---|---|
| L1 | Accounts | Production emails; sign-out/return and session isolation; full desktop/mobile journey. |
| L2 | Owner tools | Verify latest owner session, customer-tier previews and server-enforced permissions. |
| L3 | Memberships/payments | Real sandbox failed-renewal/recovery and report checkout lifecycle; live activation only after acceptance. |
| L4 | Watchlists/saved searches/alerts | Verified sender/key/receipt configuration, owned-inbox delivery, unsubscribe and retention; alert sending remains off. |
| L5 | Backup/recovery/security | Production restore proof, retention/deletion, backend wake-up, deployment monitoring; resolve recorded leaked-password-protection warning. |
| L6 | Traffic and SEO reporting | Verify Cloudflare data, Google/Bing ownership, sitemaps, indexing/search traffic and discovered backlinks; owner access. |
| L7 | Technical SEO/performance | Mobile performance, old-slug redirects, permanent pages and meaningful structured content; no private material exposed. |
| L8 | Free organic growth | £0 advertising; useful location/history pages, buyer checklist, guides, original statistics and legitimate referrals after essential launch. |
| L9 | Later commercial offerings | Featured/sponsored listings, professional services and data/API offerings remain scoped; do not confuse these with paid advertising for customer acquisition. |

Every status update should state what changed, what was actually verified and
what remains. Existing docs contain dated historical checkpoints; this backlog
does not convert those into fresh production acceptance.

## Release verification on 20 October

- Render release `5ff311490600b6c8b742fdc14e9b33e252cdc8cb` became live at 09:54 UTC and includes customer compensation, archive loading and the owner coverage API.
- Paid reports, live billing and alert sending remain disabled. No customer charge, refund or email was manually issued in this batch.
- Hosted PostgreSQL integration passed for the report-resolution tables and replacement-credit flow. Hosted public tests and Chromium evidence/account checks passed for the combined release; static publication was still running.
- Cloudflare build `290b827c-96a3-444d-8567-433234e068ff` for `514d71d` was still in progress. Do not confuse a successful Render deployment or GitHub Pages build with main-domain frontend acceptance.
- Current collection and permanent historical banking now have scheduled workflows. They do not establish complete national coverage. All-property-type banking, remaining source failures and the full-report acceptance matrix remain open.
