# Acquisition Intelligence priority audit — 8 October 2026

Audited against main at 2c8abd79537f4d011745e85ea2b9c92f5e239dde.
Publication also preserves later concurrent commits. This is a code-path audit,
not a fresh approval of the private Newbury specimen.

## Controlling owner instruction

Acquisition Intelligence quality work has priority. Do not undertake discretionary
historical catalogue recovery or unrelated expansion. Preserve completed evidence.
The broad Historical lot corpus collection workflow is paused at job level after
run 37828882901 published its checkpoint successfully. Any run already started
from an earlier workflow revision must retain its checkpoint; this pause prevents
future runs from executing the archive-traversal job. Current-stock and public
publication workflows are not changed by this patch.

Paid-report approval remains withheld. The owner’s eleven requirements and the
additional pricing-preservation requirement are acceptance criteria, not optional
enhancements. Passing tests, producing a polished specimen, or activating payment
providers cannot substitute for investment-quality approval.

## Current audit

| Requirement | Status | Implementation evidence and remaining gap |
| --- | --- | --- |
| 1. Newbury energy investigation | Partial | acquisition_energy.py and acquisition_investigation.py associate certificates with demises and connect dates, listing and rent exposure. Missing evidence is not automatically a breach. The customer endpoint does not obtain fresh certificate/exemption research. The earlier specimen used supplied research captures. |
| 2. Cross-evidence and unexpected-issue reasoning | Partial; principal release blocker | Source ledger and reasoning callback exist. legal_pack_service.py invokes a backend only when one is supplied. web_platform/review_api.py supplies neither reasoning_backend nor open_review. The operational customer path therefore does not execute open-ended review. |
| 3. Omissions, contradictions and evidence states | Partial | Evidence states, research questions, references and unresolved source coverage are represented. Recording a question does not execute the research. Source-reference validation is not semantic validation of a claim. |
| 4. Commercial investment intelligence | Partial | Existing corpus enters the analysis; guide, sale and income metrics and downside scenarios exist. Fresh comparables, covenant investigation, supported ERV/VP value and costed ownership exposures are not operational end to end. |
| 5. Investment materiality | Partial | Findings sort by decision gate, price sensitivity, routine/information and exposed income. Most priority assignments remain predefined; no operational broader review validates their relative commercial importance. |
| 6. Investment conclusions | Outstanding substantive improvement | acquisition_presentation.py assembles the opening assessment from fixed text and always adds an insufficient-fair-value statement. The resolution paragraph is also generic. Conclusions need to depend on the evidence and separate opening assessment from the final acquisition judgement. |
| 7. Premium concise presentation | Partial | Reusable five-section HTML/PDF/Word exports, media support, figures, tables and source keys exist; the previous Newbury specimen was five pages. The customer upload route does not attach the specimen photo/research package. Exact template length does not prove that all property types have an appropriate concise report. |
| 8. General-purpose adaptive engine | Partial | Property profiles distinguish vacant, leasehold, listed, reversionary, development and building-safety evidence. Multiple lease records do not automatically prove multiple current lettings. Operative lease identity/chronology and broad discovery remain incomplete. |
| 9. Real-property validation | Partial | Earlier runs covered Newbury, Wrexham, Maybrey and Dover. The Maybrey permitted-use and Dover condition-cap findings were targeted analyst discoveries, not autonomous engine discoveries. No new independent full-pack approval or new specimen rerun is claimed by this audit. |
| 10. Launch focus and paid acceptance | Quality hold implemented; paid acceptance outstanding | acquisition_quality.py returns purchase_available false independently of provider keys. The upload route and billing guard enforce the hold in the published code. This patch pauses the broad archive-recovery workflow; current-stock workflows remain unchanged. |
| 11. Meaningful reusable visuals | Implemented foundation; wider acceptance partial | Income concentration and principal-unit void charts derive from report data and are reusable. Broader chart selection and readability across materially different investments still need real-case acceptance. |

## Additional pricing requirement: partial, reuse existing structures

Existing history_database.py appends observations when guide_price, sale_price,
status or other selected fields change. historical_corpus.py already distinguishes
guide_price, guide_price_high, reserve_price, sale_price and available_price.
Savills’ published hammer_price is mapped separately from its guide. MarketContext
can calculate a sale gross yield from a positive sale price, sold status and
evidenced passing rent.

Concrete preservation gaps found:

- The observation object omits guide_price_text, the upper guide and per-figure
  evidence status/source. A range-only or wording-only revision does not trigger
  the existing material-change test.
- Event-level source_evidence is updated to later evidence. It is not a substitute
  for immutable evidence attached to each price observation.
- historical_corpus.write_rows retains absent old appearances but replaces a
  matching appearance with its new row. That protects lot existence, not every
  historical price observation.
- Property Timeline observation comparisons omit sale_price, upper guides and
  original guide wording, although some sale information is banked elsewhere.
- Original/final observed guide selection, explicitly dated guide-to-achieved
  comparison rules, per-figure status and rent-at-sale alignment are not complete.
  SOLD without a price must continue to produce no achieved-price inference.

Extend these observation/appearance records during normal collection. Do not
create a duplicate history store, undertake a retrospective backfill or treat
current snapshot fields as complete price evidence.

## Execution order from this audit

1. Make the customer analysis path execute source-grounded review and targeted
   current research, with explicit availability, failure and coverage states.
2. Improve lease identity/chronology and evidence-dependent commercial synthesis;
   retain unsupported values as unknown rather than manufacture an answer.
3. Rerun and independently assess Newbury and materially different real packs,
   checking omissions, false alarms, factual support, usefulness and presentation.
4. Add only essential missing price-observation preservation to the existing
   normal-collection and timeline architecture.
5. Resume other established launch-readiness work after these priorities.

Current verdict: NOT READY FOR PAID ACQUISITION INTELLIGENCE.
