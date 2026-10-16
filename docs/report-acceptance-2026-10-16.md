# Property Investment Reports — activation and acceptance, 16 October 2026

## Verified checkpoint

The deployed readiness endpoint still reports release `62012b58`, accounts ready,
owner access configured, billing configured, live billing false, analysis provider
not configured and paid reports not approved. The production-email confirmation
flag is false; this is an outstanding verification flag, not evidence that all
email delivery is broken. Render's latest deployment is still that release.

Existing optional-pack intake, report ownership, source-quotation validation,
credit consumption and processing-attempt persistence are reused. Stored Newbury
and other property examples are regression evidence, not fresh AI acceptance.

## Corrections in this change

- The legacy analysis service now reads the published £19 one-off price from
  the existing plan catalogue. Removed the former £25 plus VAT / £30 assumption.
  Tax treatment, infrastructure costs and gross margins remain unknown until
  reconciled; zero AI calls alone does not mean zero total generation cost.
- The existing provider sends an explicit reasoning effort (high by default),
  records it and records provider response statuses separately from cost usage.
  Incomplete output still incurs measured charges; it never becomes a complete
  report. Invalid/negative/boolean token counters and malformed usage fail closed.
- Cost estimates reject invalid counters, elapsed times and page counts. Missing
  processing measurements remain partial estimates, never complete totals.
- Full-credit-use revenue figures use the same plan catalogue as pricing. They
  are gross published-price allocations, not net revenue or profit estimates.

46 focused local tests passed: provider, analysis service, report credits and
review processing. These include failed attempts, incomplete provider responses,
source provenance and payment/ownership controls. No paid model call was made.

## Secure provider activation

In Render, select the existing `auction-sniper-private-api` service and its
Environment settings. Keep all existing values. Add/update these server variables:

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | Owner's OpenAI project API key, entered directly into Render's secret field |
| `ACQUISITION_PROVIDER` | `openai` |
| `ACQUISITION_MODEL` | `gpt-5.4-2026-03-05` |
| `ACQUISITION_REASONING_EFFORT` | `high` |
| `BILLING_LIVE` | `false` |

The pinned GPT-5.4 model is a controlled acceptance candidate, not a quality
approval. Official documentation confirms Responses, structured outputs and web
search support. Review the actual output and cost before accepting the choice:
https://developers.openai.com/api/docs/models/gpt-5.4
https://developers.openai.com/api/docs/pricing

Do not put the key in chat, GitHub, Cloudflare's public build configuration or
customer JavaScript. Save/rebuild/deploy the updated backend. Confirm the deployed
release and `analysis_provider_configured=true`; that flag proves configuration
presence only, not successful provider authentication or a useful report.

`ACQUISITION_COST_RATES_JSON` must match the exact model and effective date, with
input/cached/output USD rates per million tokens, search USD per call, documented
processing GBP per second, document GBP per page and the reconciled USD-to-GBP
conversion. Do not invent zero processing costs or an exchange rate to make the
ledger look complete. Retain raw usage even while the rate card is incomplete.
No cost-per-report or margin has yet been measured with a live provider.

## Acceptance still required

1. Run the same existing pipeline on Newbury with its original legal-pack files,
   then without a pack; also use a materially different real property.
2. Independently check Newbury's separate demises, EPC evidence, listed status,
   lease obligations and maintenance/capital exposure against actual sources.
   Preserve dates and original/revised contractual documents separately.
3. Assess income sustainability, comparable evidence, risks and actionable
   limitations in both pathways. A missing pack changes scope, not quality aims.
4. Count all attempts, failed calls, OCR/document work and any pack-update work
   in report economics. Review £19 one-offs, £15/£12 additional reports and full
   monthly-credit use (£15 Investor; £25/3 Pro before other costs).
5. Verify owner-only access to acceptance evidence and purchased-report download,
   logout/return and post-subscription access through the existing account flow.
6. Review the actual PDFs/HTML on desktop and mobile. Keep paid purchases closed
   until both evidence pathways meet the analytical gate and owner approval.

Stripe sandbox verification remains deferred, not accepted. Watch/alerts,
source reconciliation, history-job reliability and final recovery/backup checks
remain on the existing launch list; this checkpoint does not mark them complete.
