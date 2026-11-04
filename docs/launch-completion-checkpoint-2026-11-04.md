# Launch continuation — 4 November 2026

## Owner approval

Paid report launch was approved by the owner on 31 October and reconfirmed on
4 November. Live readiness returned `paid_reports_approved: true`.
The report acceptance/backlog documents now explicitly supersede their older
approval-pending wording. This does not waive per-report evidence/delivery checks
or certify completed checkout and customer-access journeys.

## Implemented

- Public catalogue loading no longer blocks authentication or restoration of an
  existing account. Late catalogue data preserves property details already
  registered by the current page. Guest and returning-user cases cover pending
  and failed catalogue requests.
- One-off report availability follows the report checkout flag independently
  of membership checkout.
- Methodology no longer says accounts are unavailable. Privacy copy describes
  native private report processing, retained reports/evidence and AI processing
  instead of the obsolete session-only Streamlit description.
- Both native Cloudflare builds and GitHub builds write the actual checkout
  revision to `deployment.json`, with no-store caching. A supplied tested
  revision must match the actual checkout before export.
- Ineligible collector follow-on events use isolated deployment concurrency
  groups. This prevents skipped runs from replacing a valid pending release.
  During this work, cancelled collection follow-ons displaced run 41885740279
  and then skipped their own deployment; run 41884796618 deployed only the
  preceding revision. Successful collection and code updates still serialize
  deployment of the latest main checkout.
- Private account CI no longer downloads raw auction archives. Its checkout
  fell from 176,265 files to 1,903 in the observed runs. Source, fixtures and
  packaged data remain available.
- Private browser CI is pinned to Ubuntu 24.04. The previous ubuntu-latest run
  failed because Playwright 1.51.1 did not support the new Ubuntu 26.04 runner,
  before it could test the website.

## Verification

Private-account workflow 41886265578 passed: 89 PostgreSQL/account/provider/
monitoring tests, plus Watch/owner-controls browser checks at 360, 390, 430 and
1440 pixel widths.

Public release workflow: https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/41887082514
The public workflow passed 527 Python tests and 3 subtests, with 14 skipped;
41 Node account-session tests passed. Chromium checks passed for evidence links,
sign-in/registration/recovery, membership history access and expiry, sharing,
and property-grid behaviour across mobile/desktop widths. Actual production
email receipt and real payment completion are separate outstanding checks.

Both public deployment jobs completed successfully. At 18:37 UTC the production
verification confirmed `https://auctiongeek.co.uk` serves revision
`cc417cf0ca3b0659734a36fb10745ccde75c3a70`. The live catalogue check matched
860 expected properties to 860 served properties and recorded 34 degraded
sources. This checks consistency with the exported catalogue, not nationwide
collection completeness. Cloudflare published 6,050 public files.

Code commits: `7eba52d` (site fixes/approval), `d75945a` (smaller account
checkout), `951d84e` (supported browser runner), `cc417cf` (deployment queue).
The active private API remains a separate release; this public deployment does
not activate saved backend payment settings.

## Outstanding operational requirements

- The website's live Stripe API key still needs secure runtime configuration.
  ChatGPT's working live Stripe OAuth connection does not supply this key.
- Seven live prices and the signing secret for the live webhook were saved
  with `BILLING_LIVE=false`. Render exhausted its build-minute allowance, so
  the saved configuration has not reached the active service. No upgrade or
  spending approval was assumed. See
  [Stripe connection checkpoint](stripe-live-connection-2026-11-04.md).
- VAT configuration, customer portal setup and end-to-end checkout, webhook,
  report delivery, subscription and history entitlement verification remain.
- Production email delivery is not confirmed; property email alerts stay off.
- Premium archive privacy and national historical coverage remain incomplete.
  This work did not declare the public repository/history archive private,
  remove raw records, disable collectors, or claim twenty-year completeness.
