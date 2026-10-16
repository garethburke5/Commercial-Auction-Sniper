# Watch launch checkpoint — 16 October 2026

The report-cost change `baed1fe6` passed GitHub application/PostgreSQL checks,
public publication and Cloudflare Workers build. Render still runs `62012b58`;
backend publication and backend deployment are distinct acceptance steps.

## Fixed in this change

- Recurring changes remain in Watch history: 100k → 90k → 100k → 90k produces
  three events, including both reductions. The old content-derived event ID
  incorrectly suppressed the second reduction.
- Existing transaction locking now covers workspace updates and observation
  advancement together. Concurrent worker/dashboard checks create one event per
  transition; a watch stop cannot be overwritten by a stale workspace write.
- A property leaving the catalogue no longer prevents its owner stopping a
  watch or clearing existing notes/targets, even after membership expiry. Other
  accounts cannot alter it, and this exception cannot start watches or add data.
- Paused watches remain visible with Stop Watch controls. Missing catalogue
  entries have a neutral description and no broken property-page link. Missing
  observations still do not become false sale/withdrawal alerts.

No new database schema, login system or reporting engine is introduced.

## Verification

20 focused local account, entitlement, monitoring and navigation checks passed.
A concurrent transition test is also included in the disposable PostgreSQL CI
suite. A real-browser test uses the account template and workspace JavaScript
with an isolated synthetic API/session at 360, 390, 430 and 1440px.
Local Chromium launch was blocked by the execution environment's socket
restriction; the browser test was run in GitHub CI instead. Run `38958010786` passed both
the PostgreSQL job and the browser job on `10a7e416`. All four viewport widths
passed the stop-watch, no-dead-link, overflow and JavaScript-error assertions.
These are isolated browser/API fixtures, not a deployed customer acceptance test.

## Still open

Scheduled monitoring is not deployed. The existing private worker records watch
changes; it does not implement saved-search match detection or customer email
sending. Email consent/verified-recipient handling, delivery/retry tracking and
end-to-end inbox acceptance remain required. Email alerts must remain advertised
as coming soon. Supabase sign-in email working is not proof of alert delivery.

The AI report provider is still unconfigured and actual report quality/cost
acceptance remains blocked. Sandbox lifecycle verification, source reconciliation,
backup/restore and final customer journeys retain their existing open status.
Paid reports and live billing must remain closed.
