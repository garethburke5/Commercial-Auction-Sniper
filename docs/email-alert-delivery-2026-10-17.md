# Daily property-update delivery — launch checkpoint

Extends the existing account, Watch, saved-search and signed monitoring worker.
No new authentication service, scheduler or paid hosting service is introduced.

## Implemented

- Explicit authenticated opt-in; email and Auth subject come from the live verified Supabase user, not request fields or user metadata.
- A private, read-only recipient view confirms that the account still exists, has a confirmed matching address and is neither anonymous, banned nor deleted. The API gains no direct access to auth.users.
- New Watch events and individually selected saved-search matches are grouped into at most one new digest per 24 hours. No historical backlog is emailed. Customer details are behind the normal signed-in account link.
- Durable outbox, serialized claims, immutable retry payload and provider idempotency key. Unknown outcomes stop before Resend's 24-hour deduplication window expires. A new digest older than 24 hours is suppressed rather than mailed late.
- Membership, consent, recipient and retained Watch/search scope are rechecked at dispatch. Unsubscribe GET is confirmation-only so link scanners cannot change consent. POST supports one-click unsubscribe.
- Svix-compatible HMAC verification on the exact webhook body, five-minute timestamp tolerance, constant-time signature comparison and event-ID deduplication.
- Delivered, failed, bounced, complained and suppressed receipts reconcile even when the receipt arrives before the send response. A later delivered event cannot overwrite a bounce or complaint. Bounces/complaints stop further delivery.
- Owner aggregate endpoint `/api/admin/alerts`; public readiness exposes configuration state only. Provider acceptance and delivery-to-mail-server are not described as proof of inbox placement.
- The existing signed `/api/internal/monitor` job services the bounded queue; a delivery failure does not erase the completed catalogue check.

## Production migration

Applied additive migration `private_opt_in_alert_digest_and_delivery_receipts` to the existing private database. Four tables have RLS and backend-only policies. `alert_recipients` is a deliberately owner-executed projection of only opted-in recipients; public/anonymous/authenticated access is revoked and the API has SELECT only. Existing tables and customer records were not changed.

Fresh installation: apply `web_platform/private_schema.sql`, then `web_platform/alert_recipients.sql` in the Supabase database. The latter requires the existing managed Auth schema. Repeat schema installation must preserve the view's read-only grants.

## Activation still blocked

Sending is disabled by default. Before setting `ALERT_EMAIL_ENABLED=true`:

1. Verify the auctiongeek.co.uk sending domain in the existing Resend account and its required DNS records. Lark account/authentication email is independent.
2. Store a sending-scoped `RESEND_API_KEY`, `ALERT_EMAIL_FROM=Auction Geek <updates@auctiongeek.co.uk>` (or another verified sender at this domain), and `ALERT_UNSUBSCRIBE_ORIGIN=https://auction-sniper-private-api.onrender.com` in Render secrets/settings.
3. Register the Resend webhook `https://auction-sniper-private-api.onrender.com/api/alerts/webhook` for email.delivered, email.bounced, email.complained, email.failed and email.suppressed. Store its `RESEND_WEBHOOK_SECRET` privately.
4. Verify opt-in and an owned-recipient test, receipt processing, unsubscribe and return to the account. Confirm actual inbox delivery, not just API acceptance. Confirm the appropriate provider quota and sending limits for launch volume.
5. Approve delivery-record retention/deletion handling and update the public availability wording before broader activation. Live billing and report quality gates remain separate and closed.

No recipient has been opted in by this change and no real email has been sent by its tests. Existing authentication email success does not establish property-alert delivery acceptance.

## Verification

Local focused tests cover digest grouping, concurrent enqueue, address changes, deleted accounts, expired membership, opt-out, removed Watch/search scope, immutable retries, deadline expiry, a delayed first send, receipt-before-response, duplicate and forged receipts, replay timestamps, unsubscribe during a provider call, account isolation and scanner-safe unsubscribe.

PostgreSQL CI checks concurrent enqueue/dispatch and the recipient view's restricted grants. Browser CI checks disabled/enabled preferences and saved-search selection at 360, 390, 430 and 1440 pixels. Deployment results belong in the launch evidence, not inferred from the existence of these tests.
