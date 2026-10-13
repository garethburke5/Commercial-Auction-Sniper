# Sign-in activation handoff

## Prepared, not deployed

The account page now supports email-code verification using the existing Supabase session architecture. Legacy authentication callbacks arriving at the homepage return to the account page. Expired callback errors produce a useful retry message, and invalid codes cannot create an application session.

Validation: `node --test web_platform/tests/account_navigation.cjs` — 17 passing tests. These are local automated tests, not evidence of deployed customer acceptance. Mobile visual verification remains outstanding.

## Coordinated activation required before merge

1. Configure the relevant Supabase sign-in and confirmation email templates to display `{{ .Token }}` clearly. Retain Auction Geek branding and existing confirmation requirements. Check new-account and returning-account templates separately.
2. Confirm the account redirect is allowed and use `https://auctiongeek.co.uk/account/` for authentication callbacks. Existing invitations may still return to the root; the code handles that case.
3. In Cloudflare build settings, configure SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and PRIVATE_API_ORIGIN from the existing project. Use only the public publishable key in the website. Keep BILLING_LIVE=false.
4. Deploy and verify code delivery, registration, sign-in/out, reload/return, private saved-property persistence and isolation using two test accounts. Verify desktop and narrow mobile screens.
5. Verify owner access separately before accepting priority 3. Email confirmation alone does not grant owner privileges.

Lark SMTP configuration has been saved and a Yahoo test invitation was delivered, initially to spam. Delivery does not establish inbox placement or successful application sign-in. Review domain authentication and actual message headers before diagnosing spam placement.

Cloudflare secure sign-in and its follow-up browser navigation timed out during this session. No Cloudflare settings were changed. Supabase email templates were not changed. This work must remain a draft until coordinated activation is possible.

## Remaining launch gates

Render was observed live on commit 104f1adafc0a14eff2e3ec379d87974d5f0251ad; latest-code deployment and the public website/API journey still require acceptance. Sandbox payment journeys, owner controls, actual report quality and costs, purchased-report retention, Watch/alert delivery, source reconciliation, backup/restore and complete mobile/desktop acceptance remain outstanding. Keep live billing and paid report purchases closed until their respective gates are approved.
