# Current website snagging: 10 October 2026

## Audit and changes

- Acuitus already had a live collector, but it was hard-coded to 17 September
  2026. It assigned that date to new October properties and published no current
  stock. Replace date matching with structured catalogue/detail dates; inspect
  every card, preserve terminal statuses and reconcile advertised counts.
- The exact source puts property information and tenancy outside `main`. The
  collector now captures those sections, isolates related-property content,
  preserves guide bounds/wording and reads labelled current rent. Liverpool
  lot 43: 29 October, guide £400,000, current rent £38,000, historic rent £40,000,
  virtual freehold, 2,828 sq ft, EPC B. These are auction particulars, not legal
  approval. All 49 source cards/details were captured and parsed; lot 40 is
  withdrawn prior. Development and reversionary interests remain in scope.
- Acuitus was labelled LIVE with zero publication and unknown discovery counts.
  Such unverified zeros are now degraded. The coverage display separates
  collection from independently checked live publication. Old proof schemas
  cannot override corrected reconciliation.
- Compound office terminology now distinguishes betting shops, post offices,
  ticket offices and booking offices in canonical data, headings, search data,
  comparable matching and the Acquisition Intelligence profile. Nearby uses
  cannot override the subject. Coral at 554 Bearwood Road is a betting-shop
  investment. Its inaccessible former upper flat is not called lettable, and
  unit size alone no longer produces a flexible-reletting claim for these uses.
- Minimum and maximum guide inputs are grouped in that order on desktop/mobile.
  Search placeholder: Town, postcode, tenant or property type. Existing filter
  semantics are unchanged.
- Owner listing permissions already existed. Reuse that server allowlist for
  owner controls and read-only visitor/free/investor/professional previews.
  Preview does not grant subscription/report entitlement or expose another
  customer's data.

## Validation and release conditions

145 focused collector, classification, source-health, financial, existing
Acquisition Intelligence and account tests passed locally. New coverage includes
auction rollover, date conflict, count completeness, withdrawn status, passing
versus historic rent, compound-office meanings and owner privilege isolation.
Actual source captures were separately replayed; software tests alone do not
establish live publication. Deployment and source-to-live verification must
complete before treating customer-facing corrections as delivered.

Owner login/preview cannot be accepted as live until the existing private
backend, Supabase configuration and owner allowlist are deployed and tested.
No paid services or report-quality approval are activated by these changes.
Historical recovery and wider feature expansion remain deferred.
