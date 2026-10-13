# Account experience activation — 13 October 2026

Implemented with the existing Supabase client and identities: separate sign-in and registration (name/email/password), confirmation, optional existing-account magic link, password recovery/update, editable display name, scoped legacy-browser export in signed-in settings, workspace timeout/retry.

Names are presentation metadata only, never authorization claims. API access and billing remain server-authorized. No new account database, password store or identity system. No live billing activation.

## Hosted Supabase configuration still required

The connector does not expose Auth configuration updates. Repository email files do not automatically update hosted Supabase.

In the existing project axoukcujpxkfvocwuaqg:

- Auth > Email Templates: copy each HTML file from `supabase/templates/` to its corresponding template. Subjects are in `subjects.json`. Templates: confirmation, magic link, recovery, invitation, email change.
- Preserve `{{ .ConfirmationURL }}` exactly. No custom token-verification endpoint is introduced.
- Auth > URL Configuration: ensure these exact allowed redirects exist, preserving any other required existing URLs:
  - https://auctiongeek.co.uk/account/
- Confirm email/password provider and email confirmation are enabled; use a server-side minimum password length of at least 12 to match the form. Keep existing users and SMTP settings intact.
- Do not merge the superseded code-only OTP proposal in PR #18 without reconciling this password-first journey.

## Acceptance evidence

15 session/navigation regression tests passed. Browser tests at 360/390/430/1440px cover sign-up, password sign-in, reset request, existing-account magic link (shouldCreateUser false), mismatched/matching password update, profile update and sign-out. Auth responses are controlled fixtures; these checks do not claim real email delivery or deployed end-to-end acceptance.

Observed Render log: GET /api/account returned 200 at 2026-10-13 21:23:21 UTC. This proves one successful backend response, not every customer journey. The Render service still reports its earlier live release 104f1ada; this UI change does not change backend code.

After installing the email templates: test new-account confirmation, wrong password, reset in the requesting browser, expired link handling, existing magic-link account password setup, sign-out/return, saved-property persistence and two-account isolation. Verify actual delivered email appearance in Yahoo/mail.com and on mobile. Keep paid launch closed until wider acceptance passes.

Browser test command: `CHROMIUM_PATH=/path/to/chromium node web_platform/tests/account_auth_browser.cjs` (requires Playwright and the project Jinja dependency). Without CHROMIUM_PATH, Playwright uses its installed browser.
