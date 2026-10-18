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
