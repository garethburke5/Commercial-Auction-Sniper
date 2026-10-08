# Launch checkpoint: payment-first analysis and evidence-led reporting

Paid Acquisition Intelligence is **not approved**. Historical recovery remains
paused; this change does not alter collectors or perform a backfill.

## Implemented

- Free snapshots now use listing information without legal-pack extraction, OCR,
  external research or model execution. A separate analysis route requires a
  verified purchase belonging to the user and exact report. Monthly membership
  has no implicit report credit. Payment redirects cannot grant access.
- Processing is claimed transactionally, completed reports are immutable on
  retry, failures retain the purchase, and automatic resubmission is limited to
  three attempts. Refund/dispute access controls remain effective. Missing
  reasoning/research providers stop processing before extraction.
- The public Streamlit prototype can no longer bypass these controls. Previously
  completed session snapshots remain downloadable.
- The shared investigation orchestrator supports initial targeted research,
  cross-evidence review, one follow-up research pass and resynthesis. Its review
  packet now includes financial context, cost amendments, lease chronology and
  market evidence. The digest binds this context as well as source material.
  Claims cannot cite sources the provider has marked unreviewed.
- Executive and final assessments serve different purposes and respond to the
  actual market evidence. Sold status alone cannot relabel a guide as a sale
  price. The template no longer assumes a named auctioneer. Ambiguous lease dates
  remain explicit without printing raw OCR fragments as investor-facing dates.
- Provider costs and margin are unknown when not measured; they are not shown as
  zero merely because an adapter does not return usage.

## Verification

130 focused engine, report, identity/billing and customer-access tests passed
locally. JavaScript syntax and Python compilation checks passed. Both existing
GitHub pipelines now include the new investigation regression tests.

Four private real-pack cases were rebuilt from preserved source-page extraction,
source hashes and previously recorded visual corrections: 540, 276, 402 and 450
pages respectively. Original PDF binaries were not re-OCRed for this pass.
The cases cover a mixed freehold/long-lease investment, conflicting retail lease
history, a new commercial leasehold, and vacant retail with repair evidence.
Previously identified restricted-use and repair-condition findings were replayed
through the review contract; this is not autonomous discovery validation.
The revised private specimen is five A4 pages with two income visuals and was
visually inspected. Source packs and private reports are not committed here.

## Outstanding

A concrete production reasoning/research provider adapter, its cost/resource
budget and full-pack live execution remain incomplete. Provider connection is
not supplied by the new orchestration contract. Independent analytical acceptance
is still outstanding on all four cases; software tests do not replace it.

Render is connected but empty; no paid infrastructure was created. Supabase Auth
and Stripe sandbox connections are verified. Monthly sandbox prices exist, but
private deployment, secure environment configuration, production SMTP, webhook
and customer-journey tests, backups and interrupted-job recovery remain necessary.
Stripe live verification is owner-dependent. Report pricing remains unactivated.

Current-collection price-evidence preservation is the next scoped data task after
Acquisition Intelligence; no deep historical recovery should displace it.
