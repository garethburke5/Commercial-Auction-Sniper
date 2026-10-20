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
| Resume historical collection | Existing workflow was explicitly disabled on 8 October. Initially resumed with two rotating ten-minute tasks; expanded to four five-minute tasks from a 50-task rotation, with persisted outcomes. Runs `39402418694` and `39403320245` completed and committed checkpoints `91b1a724` and `5ff31149`. Neither batch added appearances or addresses; total remains 270,629. The six-hour schedule is active; this is automated collection, not a promise of an agent working between conversations. |
| Publish the actual rebuilt historical database | Existing compressed database is 99,928,416 bytes; old workflow could commit newer counts while leaving the older database above its 99 MB staging threshold. Verified multipart delivery is implemented and the site reader prefers it. The rebuilt 144,216,157-byte compressed database was checkpointed successfully in five parts; legacy storage is retained. |
| Measured coverage audit | `coverage-audit-2026-10-20.json` records the current retained source evidence. A reusable audit command is included. No national denominator has been established. |

## Comprehensive coverage and historical database

Owner scope clarified on 20 October: every UK auction house, every past auction
over the preceding 20 years (currently 20 October 2006 onward), every individual
property lot and all property types. Capture advertised guide/range and reported
sale price wherever published, with outcome, auction date and original evidence.
Retain older records too. The earlier Savills-to-2013 target is a recovery
milestone, not the limit of the programme. A sold lot with an undisclosed price
must retain its sold status and a missing price, never an inferred amount.

Each rebuilt corpus now measures 20-year holdings by auctioneer and year,
including guide-price counts, sale-price counts, both-price counts and sold lots
missing a sale amount. Unknown/future dates are counted separately. This measures
stored evidence; it does not certify coverage of all auctions or all auctioneers.
The scheduled continuation has been expanded from ten tasks to 50 existing
archive tasks, including the regional Auction House collectors. It runs four
five-minute tasks per six-hour batch, preserving the existing 20-minute collection
budget and each saved checkpoint. It still needs reconciliation against the full
UK registry: a supported collector is not proof of 20-year coverage.

| ID | Job | Completion evidence required |
|---|---|---|
| D1 | Maintain the UK auctioneer/brand/branch register | Document source discovery, current status, feed relationships and missing houses. Existing registry is not a complete national census. |
| D2 | Capture every current UK auction lot | Advertised, inspected, banked and publicly displayed counts reconciled per auction; explain each exclusion/failure. |
| D3 | Preserve all property types | Commercial focus can remain in presentation, but residential/land records must be retained for the nationwide database. Current commercial collectors often discard residential results after inspection. |
| D4 | Complete historical collection | Bank individual lot appearances, not catalogue shells. Resume Savills back to 2013 and other recoverable UK sources; retain partial records honestly. |
| D5 | Repair incomplete catalogues and addresses | Latest counted archive: 270,629 appearances, 260,253 with addresses, 10,376 partial records; 618 incomplete/unreconciled catalogues and 69 fetch/parse failures, dated 8 October. These are a baseline, not newly collected totals. |
| D6 | Resolve repeat properties across auctioneers | Numbered street + full postcode + known matching tenure fallback implemented for locality/county variations; exact matching retained for ambiguous addresses. 22 Broadway regression links the retained Allsop 2021 withdrawn lot to the Savills 2026 address. Reject neighbours, ranges, unit/floor/extent differences and conflicting or unknown tenure for broader matches. All matched appearances retained without the former 100-row display cap. Live deployment verification remains required; wider reconciliation continues. |
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

## Premium history directive — evening update

The owner has authorised platform-wide premium history and one-off passes, with
useful free listings/snapshots, £0 advertising and SEO retained. See
`premium-history-delivery-2026-10-20.md` for implementation and acceptance.

| ID | Job | Current state / required proof |
|---|---|---|
| H1 | Public preview and private history API | Implemented; historical figures removed from public rendering, authorisation before private rendering. Website protection is not full archive secrecy. |
| H2 | Private archive migration | Blocking: source repository is public, including historical files and prior commits. Inventory dependencies, preserve backups, migrate collector/build access and test all public download surfaces before sales. |
| H3 | £2.99 property unlock and £5 Day Pass | Configurable prices, private entitlement schema and signed-webhook integration implemented. Sandbox products created and non-secret Render price IDs configured; real Stripe checkout-to-access acceptance remains open. |
| H4 | £10 Supporter Pass | Seven-day entitlement model present; purchase option deliberately disabled until initial journeys pass. |
| H5 | History quality | Duplicate suppression and address-range collision fix implemented; title/extent, rent conflicts, source verification and achieved-price classifications need broader acceptance. |
| H6 | History access terms and VAT | Confirm registration/tax treatment, publish appropriate terms and cancellation handling; checkout fails closed until configured. |
| H7 | Public archive SEO and analytics | Preserve current useful crawlable content; expand quality archive pages, connect Google/Bing/Cloudflare metrics and build owner conversion/revenue reporting. No fabricated metrics. |
| H8 | Browser and full customer acceptance | New mobile/desktop history UI tests added; production owner/visitor/purchaser/pass/subscriber journeys and actual Stripe payments must pass before claiming ready. |

History work does not approve or supersede R1–R9. Paid reports remain closed.

### Evening verification and collector repair

- Public workflow `39499771880` passed the platform/report suite, Chromium account/evidence/history checks, static export and Pages publication for `7739e226`. Hosted PostgreSQL checks also passed. This is not confirmation that Cloudflare has updated the main domain.
- The 17:28 historical collection batch completed successfully. This does not establish complete twenty-year coverage.
- The 17:05 current scan was stopped by its publication quality gate. A two-bedroom Landkey house had been misclassified as commercial because its location paragraph mentioned the village pub. The classifier now excludes that location evidence while retaining genuine commercial accommodation and preserving excluded records.
- The classifier regression suite passed (79 tests and 6 subtests). Reprocessing the retained failed candidate in an isolated temporary directory passed the full unchanged publication gate: 1,003 published properties; South West rich-particular coverage 66.7%. A fresh scheduled scan and subsequent live publication remain to be verified.
- Actual Stripe sandbox checkout-to-access, tax/terms confirmation and private archive migration remain outstanding. All history sales gates remain disabled.
