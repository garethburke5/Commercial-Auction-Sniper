# Commercial underwriting: implementation and validation

This responds to the owner's 18 October review of both products. The deliverable
is the reusable reporting system. Paid approval remains closed. This record is
not an acceptance certificate or a claim that the full feature is complete.

## Shared changes

- Acquisition returns now use the same identified price, fees and illustrative
  purchase-tax subtotal. Purchase-price gross yield remains a separate measure.
  Vacancy outcomes carry their capital basis and return. Annual cost-capacity
  thresholds are shown as sensitivities, not estimated expenses or promised net
  returns. Negative capacity remains a shortfall; unknown costs are not zero.
- `acquisition_underwriting.py` creates unit/income schedules, exact dated lease
  horizons and coincident break/review observations. It preserves contractual
  tenant, deposit and guarantee evidence. A trading name is not company backing.
  It retains quoted accommodation/rent bases and exact linked comparable terms,
  including uplifts, without changing the rent used at the sale date.
- Research now expressly covers unit areas, VAT evidence, rating assessments,
  recovery, operating and reletting costs. Numerical rateable values, deposit
  amounts and cost amounts must occur in their quoted evidence. These controls
  cannot make missing source evidence available or establish tax applicability.
- Fire-action findings have separate identities and precede minor balances in
  the shared analysis. Written full reports require their coverage in a main
  section. The editor must judge substantive explanation; a fact tag alone is
  not semantic approval. Completion unknown is not completion disproved.
- A rejected narrative can be revised once by default (maximum two revisions).
  The replacement is validated against the evidence and must receive a new
  draft-bound editorial review. Another rejection stays held. Provider usage
  remains inside the existing limits and ledger.
- Public snapshots now interpret scoped single-tenant, multi-tenant and vacant
  accommodation, show area-based figures and explain public-addendum scope in
  the footer. The same shared renderer supplies all cases. Full references stay
  at the end. An attributed available photo is retained in suitable short opening
  paragraphs of the written full report.

Engine build: `843df29a8202`.

## Execution evidence

No paid AI calls were made for this validation. The selected automated suite
passed 189 tests and three subtests; final CI results are recorded with the
published commit. Tests cover boundaries and
arithmetic, not independent investment judgement.

The retained Newbury input produces £195,100 identified acquisition expenditure;
£26,700 / £16,700 / £6,700 annual rents correspond to 13.69% / 8.56% / 3.43%.
At illustrative 10% and 12% annual returns, full-rent cost capacity is £7,190
and £3,288 respectively, before financing and income tax and excluding unpriced
initial capital expenditure. The main shop's £20,000 divided by quoted 993 sq ft
is £20.14; this is not a zoned rental valuation. The break/review relationship is
21 complete months from the assessment date. No fresh source extraction or
independent acceptance of the retained legal evidence is claimed.

Three additional properties were run through `analyse_uploaded_pack`, shared
interpretation and rendering without a supplied written assessment or manually
rewritten conclusions. `scripts/validate_commercial_underwriting.py` records
input/PDF hashes, engine identity, checks and the method limitation.

| Case | Distinct characteristic | Actual result |
| --- | --- | --- |
| 14 Mill Lane Industrial Estate, Alton | Single-tenant industrial freehold | One-page snapshot; £600,000 guide, £70,535 rent, 11.76% calculated gross yield, £8.75 per quoted sq ft; one-tenant exposure and published lease expiry retained. |
| Waverley Works, Sheffield | Nine-tenant industrial leasehold | One-page snapshot; £153,196 advertised rent, £4.38 per quoted sq ft; linked headlease obligations and lack of unit-level concentration evidence explained. Sold-prior status retained without inventing a sale price. |
| 5 Westminster Bridge Road, London | Vacant freehold offices | One-page snapshot; £4,025,000 reported result and £213.11 per quoted sq ft; no invented current rent or rental yield; conversion potential remains subject to consent. |

The assistant selected and indexed exact public source passages. Direct shell
HTTP capture failed DNS resolution, so captures came from the available web
reader and are labelled accordingly. The lots' detail pages contained hidden
alternative sale-status labels. Exact auction catalogue entries supplied the
Alton guide, Waverley status and Westminster result instead. This is evidence of
reusable interpretation/rendering from indexed facts, **not** automatic research
or extraction acceptance, and **not** three full legal-pack reports.

Sources: [Alton lot](https://auctions.savills.co.uk/component/bidding/20--21-october-2026-244/14-mill-lane-industrial-estate-caker-stream-road-alton-gu34-2qa-25565),
[Alton catalogue](https://auctions.savills.co.uk/auctions/20--21-october-2026-244/page-28),
[Waverley lot](https://auctions.savills.co.uk/auctions/21--22-april-2026-221/waverley-works-effingham-road-sheffield-s4-7yp-20467),
[Waverley catalogue](https://auctions.savills.co.uk/auctions/21--22-april-2026-221/page-24),
[Westminster lot](https://auctions.savills.co.uk/auctions/24--25-february-2026-218/5-westminster-bridge-road-southwark-london-se1-7xw-20969),
[Westminster result](https://auctions.savills.co.uk/auctions/24--25-february-2026-218/page-20).

## Remaining acceptance work

The paid report still needs three accepted materially different original-pack
cases through the complete process, current property-specific costs and realistic
reletting/exit analysis, original-plan review, and final editorial/layout approval.
The Newbury fallback replay has five main pages and two pages of supporting
checks/sources; it is not a new approved specimen. It still exposes areas where
source findings need better synthesis. No shortened or hand-edited conclusion is
being substituted as proof of ordinary generation.

Free generation access, quality-rejection credit/refund fulfilment, the customer
purchase/access journey and representative production costs remain open in
`report-feedback-status-2026-10-18.md`. These changes do not open checkout or
certify that a report is worth £19.
