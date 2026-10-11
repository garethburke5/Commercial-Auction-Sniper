# Property Investment Reports: optional legal packs

Status: implemented; paid launch remains CLOSED. This is an extension of the existing
`analyse_uploaded_pack` → `investigate_acquisition` service, not another report engine.
The internal names and `/due-diligence/` URL are preserved.

## Customer journey

A signed-in customer selects a catalogue property or submits a public HTTPS auction
lot URL. External sources use the existing DNS-pinned, size-bounded capture helper.
Credentials, private IPs and non-HTTPS URLs are rejected. Failed intake attempts count
against the five-per-hour limit. No AI generation or document extraction occurs during
this evidence-availability check.

The customer confirms the property address (external addresses must occur in the
captured particulars and include a UK postcode), then accepts the proposed evidence
scope. Banked history/comparable candidates are disclosed as candidates, not valuation
evidence. This pre-purchase stage is not advertised as completed research.

A verified existing purchase or included credit authorises the same investigation with
zero or more files. A scope that promises documents requires the documents. No-pack
reports investigate public and banked evidence; legal conclusions remain unverified.
The research provider receives the property particulars, market evidence, scope and
property-adaptive questions. Additional findings can request follow-up investigation.
External price/income enrichment is subject/address/quote/basis bound; conflicting
captures leave fields unknown, and rental potential cannot become passing income.

## Later documents — provisional launch policy

One legal-pack update within 30 days of report completion is included for an originally
pack-free report on the same property and sale. It creates a new report ID and retains
the original. The server links exactly one child under the same transaction lock used
for payment/processing; concurrent requests return that child. No second credit is
consumed. The child requires documents and has the existing three-attempt processing
limit. Further updates/different sales require separately agreed scope and price.
This policy is provisional pending representative generation-cost validation.

The child inherits only its explicitly linked owner's valid original entitlement;
refunds revoke both versions. Subscription expiry does not revoke a completed purchased
report/credit. There is no recursive entitlement chain and no new public database table.
Current retention-policy publication remains a separate paid-launch prerequisite.

## Validation performed

- 134 platform tests passed across the full run and targeted correction rerun; six
  PostgreSQL integration tests require their separate disposable database/CI environment.
- 37 acquisition pipeline/provider/investigation tests passed, including quote/basis and
  conflict handling. Provider doubles validate contracts, not analytical quality.
- New API tests cover confirmation, optional upload through the actual service, no unpaid
  work, owner isolation, duplicate/concurrent update requests, refunds, update expiry,
  no duplicate credits, and failed-URL throttling.
- Replayed previously captured real evidence, with NO paid provider calls:
  - Newbury: 38-document pack, 12 external captures, 737 evidence items, 22 findings.
  - The same Newbury property without documents: 12 external captures, 14 evidence
    items, four systematic findings; lease/title scope explicitly unverified.
  - Vacant Maybrey Works unit without documents: passing income remains unknown;
    lack of researched external sources is a quality blocker, not invented certainty.
- All three real-evidence replays render the existing five-page brief and HTML. They
  are NOT accepted £19 products. The open-ended provider review was not run, so their
  quality gate stays closed. Stored captures are not described as freshly researched.
- Provider token/tool usage, processing time, input files/bytes, evidence pathway and
  parent report ID remain measurable in the existing generation-attempt ledger. No
  unmeasured AI cost or margin is described as zero/verified.

## Remaining launch gates

Run the configured production research/reasoning provider on real pack and no-pack
cases; independently review specificity, source quality, conclusions, layout and costs.
Confirm production sign-in/email and the full paid sandbox journey on desktop/mobile.
Recheck source availability before purchase and make any inaccessible evidence clear.
Approve the provisional update policy against measured margins and publish retention
terms. Keep billing and report checkout/credit redemption closed until those checks pass.
