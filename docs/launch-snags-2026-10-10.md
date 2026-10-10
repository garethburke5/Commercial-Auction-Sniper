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

## Production verification

- Release `36a7004` passed 189 public-platform tests and 814 collector/engine
  tests (plus eight subtests). The existing full collection completed
  successfully in run `38042650170`.
- The resulting 10 October 10:16 UTC production snapshot contains all 49
  Acuitus lots for 29 October: 48 current and one withdrawn prior. There are
  zero detail failures or eligibility exclusions. Liverpool lot 43 retains
  the £400,000 guide, £38,000 passing rent, 9.5% GIY and virtual-freehold tenure.
- A follow-up regression confirms that a source status of Sold Post maps to
  the existing unavailable SOLD lifecycle, retaining the source wording in
  the particulars. It cannot become available again through collection.
- The corrected Coral heading, inaccessible-upper-accommodation note and
  specialist-use reletting wording are verified on the live board and detail
  page. The keyword search finds the property correctly.
- Minimum/maximum guides are adjacent and ordered correctly at phone (390px)
  and desktop widths. A £150,000–£200,000 live filter returned qualifying
  results; the phone page has no horizontal overflow. The neutral placeholder
  is live.
- Before the refreshed snapshot, the live coverage page correctly displayed
  Acuitus as DEGRADED with zero published rows, rather than LIVE. It explicitly
  distinguishes collected stock from independently verified publication.
- The live account page confirms sign-in is not activated. Owner-tier previews
  are implemented and permission-tested but remain pending live activation.
- Public deployment `38044508489` passed the source-to-live check. Browser
  verification confirmed 49 Acuitus auction cards, the withdrawn badge, the
  Liverpool detail page, its current/historic income distinction and source link.
- Live review exposed a flattened particulars block incorrectly grouped under
  VAT. The existing exact-page evidence adapter now retains Acuitus's original
  headings and summary bullets. All 49 saved source pages were processed through
  that adapter, retaining provenance. A regression checks that lease expiry and
  unexercised breaks remain outside VAT and that source metadata is excluded.
