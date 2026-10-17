# Production database permission check — 17 October 2026

Read-only inspection of Supabase project `axoukcujpxkfvocwuaqg` confirmed:

- `anon` and `authenticated` have no USAGE permission on `auction_private` and no SELECT permission on its 25 tables or two restricted views.
- All 25 private tables have row-level security enabled.
- The `auction_api` role is neither a superuser nor an RLS-bypass role.
- The session and alert-recipient views remain inaccessible to browser roles. Their owner-evaluated behaviour is not treated as a public RLS guarantee.

No customer rows, credentials or passwords were read, and no database settings were changed. These checks confirm the permission boundary; they do not replace testing two authenticated customers against the application API or proving a production restore.

Supabase's security advisor returned one warning: leaked-password protection is disabled. Its current documentation says this feature requires Pro or above: https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection. No paid plan or password-setting change was made. This remains an explicit configuration limitation, separate from the verified schema isolation controls.
