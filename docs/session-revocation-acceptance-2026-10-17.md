# Private account session revocation — 17 October 2026

## Finding and correction

The existing asymmetric JWT verifier checked signature, issuer, audience and expiry. As documented by Supabase, a signed token can remain cryptographically valid after sign-out until its expiry. Private account access now also checks the token's session ID against its subject in the current Supabase session store. This applies at the existing shared API authentication boundary, including owner actions, checkout, saves and private report downloads. Public browsing is unchanged.

The new private `active_account_sessions` view exposes only session and subject UUIDs to the backend role, with no direct Auth table access. It excludes expired `not_after` sessions and unconfirmed, anonymous, deleted or currently banned users. It is deliberately owner-executed, outside the public schema, with all public/client privileges revoked and backend SELECT only. Repeat base-schema installation preserves those restrictions. Account readiness requires the view to be installed.

No accepted-session cache is used. The already signed token must match both UUIDs on each request. Missing/revoked sessions return 401; an unavailable lookup returns a generic 503, with no credentials or database details returned. A fresh session derives the same account ID, preserving owned saves, credits and reports. Requests already authorised before revocation are not retroactively cancelled.

This reuses Supabase Auth and its existing client sign-out. It does not create a parallel login system or change token lifetimes, password rules, account records or active sessions. Inactivity and single-session policy enforcement remain Supabase's responsibility; the lookup does not claim to implement those paid-plan policies.

## Verification and deployment sequence

- Signed-token regression: valid session, revoked session, wrong subject, fresh login with the same owner ID, malformed/missing session, anonymous/expired/wrong-issuer/wrong-audience tokens, and database outage.
- Disposable PostgreSQL integration: private account save, revocation before account/report access, fresh-session return to the saved property, banned/deleted/unconfirmed/anonymous users, session expiry and read-only/private grants after repeat schema installation. Synthetic Auth tables exercise the contract; they do not constitute a real Supabase browser sign-out acceptance test.
- Install `web_platform/private_schema.sql`, then `web_platform/account_sessions.sql` (and the existing `alert_recipients.sql`) before deploying this code. The additive view does not change existing sessions or users.
- Production acceptance must distinguish installed grants and live release from an actual user sign-out/return journey. Never test by deleting a real customer's session without authorisation.

Current official reference: https://supabase.com/docs/guides/auth/sessions — “How to ensure an access token (JWT) cannot be used after a user signs out”. Reviewed the Supabase changelog before implementation; the new view uses existing UUID/timestamp Auth fields verified against the deployed project.
