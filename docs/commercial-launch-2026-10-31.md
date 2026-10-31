# Commercial launch — 31 October 2026

## Owner decision

The owner explicitly authorised making Auction Geek live, including payments,
with further product improvements following incrementally. This supersedes the
previous commercial approval hold; it is not a claim that unattended report
quality or a live transaction has been independently proved.

The owner confirmed AuctionMash live Stripe account acct_1UO227RpkJti4bUn and
Render workspace tea-db3bjhpsrm7s73bc9ar0 are the intended accounts. The owner
also confirmed that the receiving business is VAT registered. No VAT number,
rate or treatment of overseas customers has been inferred.

## Completed

- Report improvements in PR #31 merged as 980cdd9233ad9468ad24f8814cf9d49216f01451.
- Explicit PAID_REPORTS_ENABLED runtime release control replaces the permanent
  source-code refusal. Individual evidence checks, rejection/refund handling,
  ownership checks and limits remain unchanged.
- Readiness publishes separate membership, report and history checkout flags.
  The browser reads these without delaying sign-in, rather than trusting stale
  static billing settings. Missing readiness keeps checkout closed.
- Live billing rejects sandbox keys. Existing stored report snapshots refresh
  their product availability rather than retaining an obsolete quality hold.
- Membership and one-off report checkout support an explicitly configured
  inclusive manual VAT rate; active/environment/inclusive checks protect the
  advertised total. No Stripe Tax paid service has been enabled.
- Prices and membership benefits are unchanged. Public snapshots remain free.
- PAID_REPORTS_ENABLED=true, BILLING_TAX_MODE=inclusive_manual and
  HISTORY_TAX_MODE=inclusive_manual saved in Render. The resulting deploys
  cannot complete while Render build minutes are exhausted.

## Verification

92 focused tests passed, covering revised reports, activation controls, VAT rate
validation, payments, credits, refunds, subscription history, expiry and duplicate
checkouts. JavaScript syntax checks passed. These are application tests with
provider doubles, not real Stripe transactions or a completed customer journey.
PR #31's existing two GitHub test checks also passed before merge.

The full local platform suite subsequently passed: 394 tests, 14 PostgreSQL
cases skipped locally. The dedicated hosted PostgreSQL job in run 41200822203
passed. The Node session/navigation suite passed all 34 cases, including slow
and failed readiness without delaying login. The report-engine GitHub workflow
41200822089 passed. Old permanent-quality-hold text expectations were updated;
the Cloudflare fallback test required its documented pysqlite3 build dependency.

## Actual blockers, not a request for launch approval

1. Render events report pipeline_minutes_exhausted. The API is still serving
   release 87dcbcc685fc5c3b45652fae4dc202eb4ca0979e; merges alone do not update it.
2. The live Stripe account has no prices or webhook endpoints. Product writes
   twice returned an authentication/reconnect instruction, without creation.
   The owner has been given Stripe's connection-renewal link.
3. A live restricted Stripe runtime key and matching webhook signing secret
   must be installed securely, with the agreed live GBP price IDs. Current
   billing_configured=true only establishes presence, not live-mode validity.
4. Configure the confirmed business VAT rate/registration details consistently
   for memberships, reports and history, preserving advertised totals. Do not
   guess the rate or enable a paid tax service.
5. History still requires its archive/privacy and quality configuration. The
   public repository retains historical evidence: do not falsely set
   HISTORY_ARCHIVE_PRIVATE=true. Resolve this explicitly before history sales.
6. Production email confirmation and alert delivery were false on the live API.
   Do not present email alerts as operational. Check real sign-in and recovery.
7. Before activation, reconcile any sandbox customer IDs and test entitlements
   in the existing account database; test-mode records must not become real
   paid membership grants or break live Checkout.

## Live price mapping to create

| Environment key | Customer price |
| --- | --- |
| STRIPE_PRICE_INVESTOR | GBP 15 / month |
| STRIPE_PRICE_PROFESSIONAL | GBP 25 / month |
| STRIPE_PRICE_LEGAL_PACK_REPORT | GBP 19 one-off |
| STRIPE_PRICE_REPORT_INVESTOR | GBP 15 one-off |
| STRIPE_PRICE_REPORT_PROFESSIONAL | GBP 12 one-off |
| STRIPE_PRICE_PROPERTY_HISTORY | GBP 2.99 one-off |
| STRIPE_PRICE_HISTORY_DAY_PASS | GBP 5 / 24 hours |

Webhook target: https://auction-sniper-private-api.onrender.com/api/billing/webhook.
Use the event types handled in Billing.webhook, verify delivery and fulfilment,
and configure the customer portal. No credentials belong in the repository.
Enable BILLING_LIVE only with matching live configuration. Confirm runtime
readiness, authenticated checkout, signed fulfilment and account reopening.

Pause checkout with BILLING_LIVE=false; pause new reports independently with
PAID_REPORTS_ENABLED=false. Previously paid customer access remains governed
by existing ownership and payment state, not a marketing flag.

Facebook and Instagram were explicitly excluded from this launch work because
the owner confirmed their posts are already live. No social settings changed.
