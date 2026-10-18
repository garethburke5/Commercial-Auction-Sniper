# Auction Geek report feedback: implementation and outstanding work

Audit date: 18 October 2026. Reviewed source baseline:
`6a1f55b23b50a9449cf52aeff576402158142205`, including the shared reporting change
`e44b00c39e3ec830643548835b95df2a1b437069`.

The deliverable is a repeatable Snapshot and Full Investment Report service for
Auction Geek. Newbury is a regression case, not the product. The owner's feedback
is binding throughout research, interpretation, writing, presentation, charging
and delivery. The intended Full Investment Report price remains £19. Paid
approval remains closed; this audit grants no product approval.

## Which instructions control

- Later explicit owner corrections supersede earlier requests. All full sources
  now belong together at the end; optional small numbered references may link
  there. The previous instruction to put full labels beside findings is retired.
- Explain supported facts directly in professional British English. Explain
  organisations and specialist terms on first use. Keep material uncertainty
  with its practical consequence; remove repetitive defensive qualifications.
- Earlier asking prices are concise factual history. They are not automatically
  a discovery, evidence of undervaluation or a reason for extended speculation.
- Identify the individual units in a lot. A certificate for one unit in that
  lot is not an unrelated property's EPC. An unsuccessful search does not prove
  a breach. Listing alone neither proves exemption nor the cost of compliance.
- A title exclusion or an asbestos clause is not itself a defect or hazard.
  Establish the evidence, extent, date and commercial consequence before giving
  it prominence. Historical findings must not silently become current liabilities.
- The free product must be useful. The paid product adds depth and commercial
  analysis. Neither should manufacture confidence, imply exclusive sources or
  hide a material unknown for marketing effect.
- Newbury's later source review qualifies the earlier instruction to preserve
  its asbestos/title findings: the positive sample was historical and located
  on the first floor; comparison of the lease/title plans did not establish loss
  of either commercial letting. Preserve the evidence, not the old implication.

The detailed acceptance gates in `report-product-rejection-2026-10-18.md` remain
required, subject to these later corrections. Older implementation records are
dated evidence, not competing current instructions.

## Evidence levels

**Implemented** means a specific reusable behaviour exists in the inspected
code. **Partial** means some implementation or specimen evidence exists, but the
complete requirement has not been demonstrated. **Open** means the necessary
customer outcome or acceptance evidence is missing. A prompt instruction is not
proof the model follows it. A test fixture is not a commercial product review.

| Owner requirement | Current evidence | Status and remaining proof |
| --- | --- | --- |
| Apply feedback to the whole feature | Shared modules serve the report pathways; `acquisition_quality.py` keeps paid purchase closed. | **Partial.** No accepted end-to-end product across the required property types. |
| Natural, clear, useful prose; each paragraph adds value | `acquisition_narrative.py` has writer and draft-bound editor stages. `acquisition_editorial.py` catches known prose defects. | **Partial.** Current polished specimens were composed by the assistant. Ordinary generation has not demonstrated the same standard; phrase checks do not assess meaning. |
| Explain agents, organisations and terms | Shared writer/editor instructions require this. | **Partial.** Needs independent review of untouched outputs, including headings and captions. |
| Remove bureaucratic openings and repetitive process caveats | Shared writer instructions and revised specimens comply in important places. This audit found the account API still prepending a public-evidence disclaimer to finished free reports; that wrapper is removed in this change. | **Partial.** Inspect the complete website journey as well as downloaded files. An exported specimen alone missed this defect. |
| Full sources at the end, optional small linked numbers | `acquisition_evidence_links.end_references`; PDF/HTML/DOCX rendering and the source-position/link tests in `tests/test_report_editorial_contract.py`. | **Implemented for the current shared report renderer.** Older separately stored formats are not retrospectively certified. |
| Convenient supporting evidence with real destinations | `web_platform/review_api.py` and `web_platform/static/report-evidence.js`; ownership, restrictions, expiry, revocation and old-link tests. | **Implemented for retained extracts/page text.** Original PDF page viewing is not implemented. Fresh purchased-report journey still requires acceptance. |
| Concise price history; distinguish ask, guide and reported sale | Shared writer/editor instructions and source-bound price fields; edited examples. | **Partial.** Detection of an earlier price in every fresh case is not proven. A listing-added date cannot by itself establish the price on that date. |
| Avoid repeated facts, findings and dates | Exact duplicates merge; ambiguous dates are excluded from timelines; specific regression tests exist. | **Partial.** Repetition in different words and useful versus redundant cross-references still require semantic review. |
| Accurate units, ownership and rental income | Lease chronology, supporting-instrument rejection, rent reconciliation, public/private separation and matching safeguards exist. | **Partial.** Conflicting packs have been withheld; they have not become accepted reports through a general reconciliation process. |
| Explain each unit's EPC position accurately | Energy/source matching safeguards and explicit writer/reviewer instructions; corrected Newbury interpretation from retained evidence. | **Partial.** No accepted unseen multi-unit example proves reliable matching, extent interpretation and applicability together. |
| Investigate title issues before describing a defect | A title exclusion alone is no longer an automatic decision blocker. Newbury plans were visually compared by the assistant. | **Partial.** Production accepts recorded visual dispositions; this audit did not find an automatic plan-comparison stage supplying them. Manual visual review is not automatic capability. |
| Ground asbestos concerns in actual evidence | `acquisition_property_evidence.py` requires an identified positive sample page and retains location, material, score and date; unfamiliar synthetic sample tests exist. | **Partial.** A general process must also connect historical location, present demise, condition and responsibility. Newbury needed visual/manual interpretation. |
| Distinguish confirmed problems, potential risks and routine provisions | Finding materiality and evidence fields; shared review instructions; routine title handling. | **Partial.** No field or number of findings proves the classification is substantively correct on fresh packs. |
| Independent useful commercial analysis | Market records distinguish price/rent bases and preserve tenancy qualifications. Newbury has researched auction comparisons. | **Partial.** Sustainable rent, reletting demand and exit analysis have not passed the required diverse full-report set. A reported sale comparison is not a valuation. |
| Property-specific acquisition and ownership costs | Deterministic fee, tax, recovery and cash schedules; historical spend stays separate from a current budget; unknowns remain unknown. | **Partial.** Generic percentages cannot replace missing property costs. Actual current liabilities and recovery need source-backed assessment in accepted cases. |
| Explain tenant loss with meaningful visuals | Shared income, lease-event, comparison and vacancy charts; uncertain dates withheld and arithmetic tested. | **Implemented calculations and rendering, partial product acceptance.** Input interpretation and practical usefulness still require review per property. |
| Polished 3–5-page main paid report; concise useful snapshot | Shared renderers, latest visually reviewed Newbury specimens and Aylesbury regression. | **Partial.** No accepted diverse automatic report set. Page count or visual inspection alone does not establish £19 value. |
| A genuinely usable free Snapshot pathway | Completed public-evidence results can export without purchase; private evidence is excluded. | **Partial.** `run_analysis` still requires a paid entitlement except for owner validation. Free export of an already generated result does not prove a complete customer-accessible enhanced Snapshot generation journey. Define and implement bounded free research before calling this complete. |
| Insufficient evidence costs the customer nothing | `evidence_sufficiency` classifies results; closed checkout prevents new paid sales. | **Open fulfilment gap.** Classification does not restore consumed credits or initiate cash refunds. The inspected processing/credit code has no quality-rejection restoration flow. Handling externally received refund events is a different behaviour. |
| Reliable generation and correction | Source review, writing, editorial checks, processing attempts and recovery exist. | **Partial.** The pipeline records a failed editorial verdict and holds the result; it does not run a bounded correction/re-review loop. Reliable final delivery still needs demonstration. |
| Sustainable generation cost | Provider usage ledger and `web_platform/report_costs.py` preserve unknown rates/usage. | **Open acceptance.** No complete representative production costs, retries and failures reconciled to establish margin at £19. Offline formulation remains independent of API credit. |
| Purchase, access and ownership work together | Intake, ownership, credits, refund/dispute revocation and post-membership access have code and regression evidence. | **Partial.** Actual accepted generated reports must complete purchase/redemption, download, logout/return, membership expiry and rejection/refund journeys. |
| Prove transfer to unfamiliar properties | Multiple real evidence sets exist; incomplete packs were withheld. Aylesbury is now a regression case. | **Open acceptance.** No three accepted full reports across materially different types and no untouched full-pack holdout. Rejected cases must remain in the record. |

## Corrections made by this audit

1. Retired the contradictory inline-source instruction in the acceptance brief.
2. Linked this status record from the product standard, latest editorial brief
   and consolidated launch priorities so requirements do not depend on which
   historical note happens to be read first.
3. Removed the account API's extra opening disclaimer for completed free
   Snapshots. The shared report retains its scope explanation at the end. Private
   validation labels and incomplete/failed job notices remain in place.
4. Recorded the free-generation, visual-review, correction-loop and quality-refund
   gaps explicitly instead of treating exported documents or written requirements
   as evidence that these customer behaviours work.

These are specific corrections and an audit. They do not complete the product.

## Working order and proof required

1. Complete a materially different original-pack case through shared extraction,
   research, interpretation and writing. Record required human/visual inputs;
   do not disguise fixture-specific interpretations as engine capability. Use
   retained evidence for offline development without making API credit a blocker.
2. Close the interpretation and editorial failures exposed by that case, including
   how flagged drafts are corrected and reviewed without unbounded spend. Freeze
   the shared process before the untouched holdout. Retain failures as evidence.
3. Complete the free Snapshot customer route and insufficient-evidence credit/
   refund lifecycle, including retries, ownership and no double reimbursement.
   Do not open paid checkout to test whether these protections work.
4. Demonstrate the required diverse accepted report set, production equivalence,
   measured cost and the complete customer journey. Review every customer-facing
   surface, including API wrappers, account pages, PDF, HTML and evidence views.
5. Seek owner approval of the demonstrated product. Until then all paid-report
   release claims remain false, regardless of commits, test counts or deployments.

Report progress against the requirement and actual evidence. Do not mark a row
complete because its instructions were added to a prompt, an edited specimen
looks better, or a test asserts a field. The owner should not need to keep
supplying the same editorial and analytical corrections.
