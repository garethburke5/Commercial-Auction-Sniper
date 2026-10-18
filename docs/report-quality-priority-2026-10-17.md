# Property Investment Reports — quality-first checkpoint, 17 October 2026

**Historical checkpoint. Updated acceptance requirements:** the two 18 October
Newbury customer specimens have been rejected for paid release. The controlling
rejection, free/paid product distinction and next-submission gates are in
[`report-product-rejection-2026-10-18.md`](report-product-rejection-2026-10-18.md).
Provider/key status below records the earlier inspection, not the current blocker
to report formulation. Offline quality work does not depend on API credit.

The owner has explicitly reprioritised report quality ahead of further source expansion and the statistics dashboard. Paid purchases remain closed. The next product milestone is independently reviewed, useful real-property reports, not another UI polish or green test count.

## Confirmed defects and corrections

1. The provider previously sent every research question in a single web call and attached the resulting actions to every question. A general search could therefore make unsearched topics appear investigated. Each question now receives its own bounded research call and completion receipt. Exhausted search capacity produces `not_attempted`, which does not close a coverage gap. A failed tool action is not a completed investigation.
2. Numerical research fields were validated against the entire captured page. A figure from another unit or property could support an unrelated quotation. Price, rent, area and score now require the number in the actual supporting quotation. Non-finite, negative and boolean numeric fields are rejected. This validates provenance, not semantic truth or property identity.
3. Source-batch review omitted the evidence-scope and financial context supplied to final synthesis. Batches now retain both, including the no-pack limitation and assessment price/rent basis.
4. Source captures are cached for the single report and shared across its questions. Defaults are 12 search tool calls, 24 attempted distinct URL captures and three selected captures per question; unchanged overall ceilings are 32 provider requests, 160,000 output tokens and 900 seconds. Skipped captures are explicitly recorded. These are validation budgets, not evidence of adequate investigation or acceptable cost. No provider calls were made in this checkpoint.

## Verification and its limits

- 921 tests and 19 subtests passed across the full root test suite and report processing, intake and chronology tests. One dependency deprecation warning remains. An initial local Stripe-client test failed because the local HTTP client lacked SOCKS support; rerunning with the existing installed dependency resolved it without changing production code or network settings.
- The archived Newbury source set was replayed through the existing engine, with 39 extracted documents and four demises; the no-pack path was also exercised. Neither had fresh AI reasoning, and neither was approved. Original/superseded documents were retained in this diagnostic, so it is not an operative-lease or investment conclusion.
- Eleven of twelve archived external records passed the tightened quotation check. The old Arcade EPC record was rejected because its quote did not support its attached area/score. This is a defect in the archived evidence record, not proof that an EPC is absent or invalid. Fresh source capture is required before relying on those attributes.
- The no-pack run explicitly retained nine uninvestigated questions. Missing legal documents were not treated as non-compliance and the product hold stayed closed.
- Production readiness returned `analysis_provider_configured=false`, `paid_reports_approved=false` and `live_billing_enabled=false`. Read-only Render inspection confirmed the OpenAI key/provider/model settings were absent, with no linked environment group. No secret values were revealed.
- Non-secret Render settings have now been merged: `ACQUISITION_PROVIDER=openai`, `ACQUISITION_MODEL=gpt-5.4-2026-03-05`, `ACQUISITION_REASONING_EFFORT=high`. The existing pinned model remains an acceptance candidate, not a claim of the best model or approved report quality. `OPENAI_API_KEY` still needs secure owner entry. Configuration presence and deployment alone do not prove successful provider authentication.

## Required real-report acceptance

Use the same production analysis pipeline for all cases. No property-name branches, inserted analyst narrative, mock model responses or manually authored conclusions may be presented as autonomous output.

1. Newbury with the original pack; Newbury without a pack; at least one materially different commercial investment, preferably vacant or single-let. Identify every property/demise and evidence date before interpretation.
2. Check Newbury EPC address/extent differences, listed-building evidence, operative leases and variations, occupation dates, repair exposure and the interaction between them. An EPC for one unit does not clear another; a missing search result is not a legal finding.
3. Reconcile current versus historic/potential income, tenant legal identity, breaks/expiry, service-charge recovery and title/lease obligations where documents exist. In a no-pack report, label auctioneer claims as such and retain contractual unknowns.
4. Assess rental sustainability, local demand, relevant comparables and property history using dated attributable evidence. Keep asking, guide and achieved prices separate. Do not manufacture ERV, vacant-possession value, works costs or a maximum bid to fill a table.
5. Prioritise the few matters affecting income, capital expenditure, finance and exit. Each material conclusion needs evidence, commercial consequence, confidence/limitations and a proportionate next action. Avoid both omissions and false alarms. A material unsupported assertion or missed decision-changing risk fails acceptance.
6. Review the actual HTML/PDF on mobile and desktop: concise opening assessment, legible financial tables, prioritised risks, useful property-specific insight and a detailed evidence appendix. A fixed page count must not hide material evidence.
7. Judge the no-pack report on usefulness, not just successful execution. If obtainable evidence cannot support more than generic warnings, do not deliver it as an accepted Full Investment Report. Available packs deepen the same analysis; they are not mandatory.
8. Record all model/search/OCR/document work, retries and failed attempts. Measure cost per completed report and full-month-credit economics before confirming commercial margins. Unknown costs stay unknown.
9. Prove purchase/credit entitlement, generation, owner-only download, logout/return and post-membership access. Keep the independent paid-product gate closed until actual output has been reviewed and the owner approves it.

Provider activation still requires secure credential entry. No API key belongs in this repository, customer JavaScript, Cloudflare public builds or chat. External research results and private pack contents remain outside public Git history.

Official configuration references checked: https://developers.openai.com/api/docs/models/gpt-5.4 ; https://developers.openai.com/api/docs/guides/tools-web-search ; https://render.com/docs/configure-environment-variables .
