# Report rebuild implementation and evidence — 18 October 2026

The shared engine has been changed and an eight-document review set generated across seven properties. This supersedes the earlier brief-only implementation status. It does not reverse the paid-product rejection. The price remains £19; `paid_report_status` continues to deny every purchase.

## Implemented

- A five-section investor brief with a separate source appendix. Income concentration, exact lease events (including reviews), tenant-loss exposure, rental comparisons and achieved-sale headline yields use deterministic calculations and charts.
- Distinct labels for reported sale, guide, marketing ask and achieved comparison. The subject address is no longer reused as a neighbouring comparison's chart label. Large quoted monetary amounts retain full decimal formatting rather than failing validation because of scientific notation.
- Invalid/amended dates become explicit unresolved-date text and do not become timeline dates or deadlines. Source wording stays in the evidence record. Distinct lease findings identify their unit; actual duplicate findings merge.
- Defined break dates can join the operative power on a different page of the same document. Source references cover both pages. Definitions never join across separate documents.
- Registers, variations, alteration licences and supporting letters do not create extra lettings. Unidentified lease documents cannot reconcile income by accidental arithmetic. A conflict among rent amounts cannot be overwritten by a single legacy summary.
- Actual principal-tenant rent loss is shown for six and twelve months, before unquantified holding/reletting costs. Historical expenditure requires a reconciling printed total and remains distinct from current net landlord costs. Known tax enters the partial capital subtotal even when fees are unknown. No unsupported net yield is claimed.
- Public-evidence reports become concise free Snapshots. Disclosed half-rent seller top-ups, conflicting public rents and potential rent on vacant property receive source-bound interpretation. Incomplete pack results are concise evidence checks, labelled no charge, instead of padded full reports.
- Owners can download an explicit finished public-evidence Snapshot without a purchase. The API checks ownership, processing state, explicit scope, documents, lease data and retained legal-pack evidence; inconsistent or private pack scope fails closed. UI downloads use the same server decision.
- The research provider instructions now seek primary auction results as well as lot details, preserve concession/ERV distinctions and capture comparable tenancy qualifications. No provider requests were used in this validation run.

## Actual acceptance set

| Case | Pathway | Result | Remaining limitation |
| --- | --- | --- | --- |
| Newbury mixed-use freehold | Retained 547-page pack evidence plus newly captured primary commercial comparison | Five main pages plus appendix; four meaningful chart types | Original extraction was replayed, not rerun; new combined evidence still needs independent review, current expense budgets and release acceptance |
| Newbury | Retained public evidence plus fresh comparison | Free Snapshot | Contractual terms remain unverified |
| Bearwood betting investment | Original supplied pack, 90 pages | No-charge incomplete evidence result | Operative rent, property extent, current variation and commercial evidence unresolved |
| Northgate retail/upper parts | Original supplied pack, 254 pages | No-charge incomplete evidence result | Renewal/incorporated lease and retained upper-floor interests require reconciliation; cross-page tenant break now recovered |
| Shipley leasehold retail | Original supplied pack, 232 pages | No-charge incomplete evidence result | Headlease/draft/occupational lease hierarchy and current rent unresolved |
| Wallington trade counter | Current capture of retrospective auction particulars | Free Snapshot | Headline income includes disclosed seller top-up during half-rent period; contractual funding unverified |
| Bedford shopping arcade | Auction particulars and auctioneer result article | Free Snapshot | Published rental totals conflict; no invented reconciliation |
| Trowbridge vacant listed former bank | Current primary auction particulars | Free Snapshot | Marketing ERV is not passing rent; no reliable price taken from a blank template |

The three additional original packs total 576 pages. All original pack hashes, extracted pages, captured public sources, input reports, outputs and validation manifests are retained privately. Private source material is not committed here.

## Newbury commercial evidence

The Savills result catalogue records a £455,000 hammer price for 30/31 Northbrook Street on 27 January 2026, with £50,000 advertised annual rent. The calculated headline gross ratio is 10.99%, versus 14.05% on the subject's £190,000 reported sale and £26,700 stated rent. The 3.06 percentage-point spread is not a valuation discount. The comparator occupies a different pitch and its particulars disclose a rent-free period until June 2026 and a fifth-year tenant break. Adjustments, incentives, actual condition and legal liabilities remain material.

Primary captures:
- https://auctions.savills.co.uk/auctions/26-27-and-28-january-2026-216/page-24
- https://auctions.savills.co.uk/auctions/26-27-and-28-january-2026-216/3031-northbrook-street-newbury-berkshire-rg14-1dj-20243

Additional searched lots without published achieved prices were not promoted into achieved comparisons. An older brochure was not treated as current merely because a search result had a recent crawl date.

## Verification and limits

147 targeted report/provider/access/processing tests passed. A further 62 legacy ingestion/provenance/lease/credit tests passed (the groups overlap; do not add them as a unique total). JavaScript syntax and changed Python modules compile. The final PDFs are rendered and visually inspected; their page counts and evidence classifications are recorded separately.

The validation runner reports the actual input digest and engine identity. Newbury was a retained-evidence presentation replay with a fresh market supplement. The other packs used real OCR and cached-page re-extraction; the public-only cases used captured auctioneer material. These are not provider-cost or live paid customer acceptance results.

## Still required before paid release

1. Independent review of the combined source evidence and report conclusions, including Newbury's unresolved dates, EPC extent, repair recoverability and actual expense budget.
2. At least three substantively accepted full reports across differing property types and an untouched holdout. The incomplete cases are failures correctly withheld, not paid-product passes.
3. The no-charge outcome must be completed through the payment/credit fulfilment lifecycle before sales reopen. This change classifies and presents the result; it does not claim an automatic cash refund or consumed-credit release has been implemented.
4. Real generation cost reconciliation and complete purchase/credit/download/logout/reopen acceptance. No live purchase was made in this run.

Continue with report quality before source expansion or the owner analytics dashboard. The consolidated launch brief retains the other priorities.
