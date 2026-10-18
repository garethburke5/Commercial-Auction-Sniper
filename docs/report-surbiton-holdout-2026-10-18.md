# Surbiton holdout: 5 Victoria Road

User-selected test property: Savills lot 258, 21 October 2026. The test began
with deployed engine build `843df29a8202` and the current production catalogue.
The untouched initial PDF, JSON, input and file hashes have been preserved.

## Verdict

The baseline failed. It called the freehold long leasehold, used the seller-
topped-up headline rent as the income measure, and omitted useful quoted
evidence about the top-up, published break, tenant history and EPC rating.
This was a substantive intake and interpretation failure, not just bad prose.

The revised shared engine produces a useful initial snapshot from indexed
sources. This does not pass the full paid-report acceptance gate. No legal pack
was supplied or accessed; Savills requires login. No authenticated owner
production report was generated in this test. Source discovery and indexing
were performed by the agent, not by the application's research provider.
There were no paid AI calls. No customer narrative was supplied to the engine.

## Findings that matter

- £490,000 auction guide; actual tenant rent £58,500, giving 11.94% gross.
- The £62,500 headline includes a seller contribution equivalent to £4,000
  annually until the fixed uplift. Cattaneo's brochure gives 4 February 2028.
  How the seller pays and protects that contribution requires the conditions.
- Freehold sale; the upper parts are sold on long leases. Residential rental
  income from Cattaneo's earlier combined marketing must not be added here.
- Cattaneo describes a year-ten tenant break from the August 2025 commencement:
  2035 is an indicative year, not an established contractual break date.
- Surbiton Hardware Ltd, company 16336552, was incorporated 24 March 2025.
  First accounts are due 24 December 2026. Deposit/guarantee evidence matters;
  active registration is not evidence of credit quality or rent collection.
- Brochure areas: 1,398 sq ft shop and 2,240 sq ft basement. The brochure's
  rent-per-Zone-A printed figure contains a transcription/typographic anomaly;
  it must not be copied as an established rental comparable.
- Brochure EPC C (54) relates to No. 5. It is marketing evidence, not inspection
  of the certificate or proof of its current validity/extent.
- Historic England list 1358455 includes Nos. 2-8 consecutively, hence No. 5.
  Grade II listing is established; no building defect is inferred from it.
- The earlier £1.575m asking price covered Nos. 4 and 5 plus four flats. It is
  not a like-for-like reduction to the £490,000 guide for this lot.

## Shared changes

1. Reconcile stale stored passing-rent and tenure fields only against explicit,
   quoted, subject-matched current auctioneer evidence; retain the old values.
2. Preserve current tenant rent ahead of topped-up headline rent in the Savills
   collector. Do not classify a freehold as leasehold because upper parts were
   sold on long leases. Use the lot page title when the HTML H1 is a login modal.
3. Carry published rent concessions, lease horizons, brochure EPC information,
   company dates and their sources into shared interpretation/writing inputs.
4. Keep marketing EPC ratings separate from inspected certificates; identify
   combined-property asking prices as a different scope.
5. Lead the free snapshot with the actual rent calculation, explain the
   investment-specific evidence, and retain clickable sources at the end.

## Validation and remaining gates

174 selected regression tests passed after the changes. The same frozen input
was replayed before adding the separate Historic England source to the final
snapshot. The original case's `Freehold` text assertion was case-sensitive;
the rerun correctly prints `freehold` and stores tenure `Freehold`. This is
recorded rather than altering the original failed specimen or its manifest.

The final one-page PDF passed content checks and visual inspection. This is
not proof of autonomous source extraction, legal-pack analysis, valuation,
cost completeness, paid delivery or full editorial quality across properties.
Legal-pack next checks: operative lease/break, deposit or guarantee, top-up
mechanism, upper-part leases and repair recovery, title, insurance, actual EPC,
special conditions and completion charges. No unsupported asbestos, fire or
title defect has been introduced.

Paid purchases remain closed. A polished snapshot is not a paid-report pass.

## Legal-pack continuation

Eleven user-supplied originals were ingested without AI-provider calls. The untouched first run accepted ten documents, flagged the legacy CPSE DOC for conversion, and flagged local-search page 34 for visual review. That page was subsequently inspected as a highways map. Local LibreOffice conversion preserved the CPSE original and both hashes; this is not evidence that production now converts legacy Word automatically.

The first legal-pack PDF is rejected. It failed to explain the contractual rent provisions and the separate proposed long lease, missed material seller costs and recovery restrictions, and generated vague generic text. The independent reviewed assessment is an analyst-authored benchmark; it must never be presented as unattended engine output or paid-product acceptance.

Shared corrections in this continuation:
- DOCX extraction retains paragraph/table order, so questions remain beside replies. Merged cells are emitted once while distinct cells with identical text remain separate.
- A bounded parser calculates explicit percentage seller contributions from special conditions and the assessment price. Conflicting percentages are not silently selected. It does not claim to recognise every fee or resolve later addenda.
- Service-charge caps retain their whole definition, indexation and cessation wording. A nearby cap is not automatically interpreted as a cap on every repair expense.

Validation: 119 selected tests passed, plus 3 subtests. The converted eleven-document rerun captures the percentage seller contribution and service-charge cap. The original and revised machine outputs, input hashes, conversion record and reviewed report are retained privately; no legal-pack documents are published in this repository.

Still failing commercial acceptance: general rent-schedule/date conflict interpretation; occupational lease versus proposed long-lease reconciliation; comparison of coloured plans and basement footprint; full charge and SDLT reconciliation; checking attachments referenced in CPSE; evidence-bound natural prose without reviewer repair. No external enquiries were sent, no bid or purchase was made, and the paid gate remains unchanged. The Savills secure sign-in submission did not produce a visibly authenticated session; use of the supplied pack is recorded separately from site retrieval.
