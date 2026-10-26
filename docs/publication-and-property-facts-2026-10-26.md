# Publication recovery and ordinary property examples — 26 October 2026

The SEO implementation's full CI run found a glossary regression: large-image
preview metadata was applied to all public pages. Commit
`f2c2b369d4397759ee398404c813a4c7ff44d8f4` scopes it to property pages; snapshots
retain their own setting. Existing glossary behaviour and its test are preserved.
Local focused checks: 73 passed. Remote run 40343795807: 489 passed, 14 skipped,
3 subtests passed. Its subsequent browser step timed out during Ubuntu package
downloads before running any browser checks. Install only the pinned Chromium
browser on ubuntu-24.04; keep every browser test and its timeout. The runner log
shows the required runtime libraries were already installed.

## Data corrections

The source pages were checked on 26 October:

- [103 Hilderthorpe Road](https://www.pugh-auctions.com/property/202609031528sq_le3f):
  published rent is monthly with VAT stated separately; there is also an expressly
  additional current advertising-hoarding payment. £250 × 12 + approximately £750
  gives approximately £3,750 annually before costs, not £250 annually. This is a
  calculation from advertised figures, not verification of actual rent collection.
- [1 Hamel House](https://www.pugh-auctions.com/property/202603031215sq_q27a): an
  office building; references to industrial warehousing describe its surroundings.
  No current rental income is inferred from the earlier asking rent.

The reusable rules now recognise a VAT qualifier before a rental period, and can
add one explicitly additional current advertising payment to one passing rent.
They do not add it to a stated total or whole-property income, invent an annual
period, or include historic income, potential rent, neighbouring income or costs.
Property classification uses the asset description with surrounding-area prose
removed. A warehouse with ancillary offices remains industrial.

Validation: 74 focused tests; full local collector suite 1,251 passed plus 22
subtests. End-to-end Pugh parser checks on the stored particulars produce £3,750
for Hilderthorpe and Office/no current rent for Hamel House. Existing published
data requires a fresh collection; no historical snapshot timestamp was changed.
These collector changes trigger the existing production collection workflow.

## Separate custom-domain blocker

Cloudflare's Workers build still fails immediately without an error explanation
in its GitHub check. GitHub's browser session is authenticated as garethburke5,
but Cloudflare's sign-in flow remains blocked. Read-only inspection of the
repository's Actions configuration found no existing Cloudflare deployment secret
or environment secret to use as an alternate deployment route. No new credentials,
permissions, paid plan or infrastructure were created. A successful GitHub Pages
run must not be described as a successful auctiongeek.co.uk deployment.
