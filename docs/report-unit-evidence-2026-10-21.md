# Shared report improvements — 21 October 2026

Paid reporting remains unapproved. This is implementation and offline evidence,
not a claim that an automated £19 report has passed customer acceptance.

## Delivered changes

- Both report presentation paths retain a computed unit-income schedule. It
  distinguishes letting rent from ground rent, accounts for all reconciled
  income and shows each share. Unresolved lease records have no invented total
  or shares; missing ground rent cannot become zero. Public snapshots do not
  receive these private schedules.
- Unit-specific EPC tables identify the certificate found for each letting,
  its rating, expiry and recorded scope/address qualification. They distinguish
  an unmatched certificate from a non-existent certificate. A known low rating
  can no longer be described as a missing EPC by the interpretation layer.
- Implicit EPC matching requires the exact unit/address, optionally followed
  by a comma-separated locality. Number 1 cannot match 11, 1–3, an upstairs
  flat or a different extent merely through a substring. Explicit scoped
  source associations remain supported.
- Standard Law Society business-lease particulars are read from their labelled
  opening page: tenant, property, annual rent and valid term dates, including
  separated year boxes. Every field retains the original page evidence. A
  different competing rent still prevents automatic selection. Annexed forms,
  monthly amounts and impossible dates do not become current annual rent or
  deadlines. Registration numbers and OCR margin digits are not tenant names.
- Full references remain together at the end. The renderer records physical
  section starts for validation, separating main-brief overflow from additional
  source pages. No type-size reduction or finding deletion is used to pass.
- The reported-sale price label no longer carries an irrelevant completion
  qualification. Historical source captures themselves are preserved.

## Offline checks and limitations

- 227 report/extraction/editorial tests and three subtests passed, including
  preservation of source references and prevention of duplicate EPC commentary.
- The retained Hartlepool extraction was rebuilt against all 16 matching
  original-file hashes, without a provider or analyst-note injection. The
  previously missed shop rent, named tenant and lease term now reach the
  investigation. The full income remains unreconciled and the result remains
  a no-charge research update. This is not a successful paid report.
- Newbury presentation replay: five physical main pages plus one appendix
  pages. Surbiton remains a research update with an editorial blocker. All
  three cases remain ineligible for charging; failures are retained.
- These are retained-evidence checks. No fresh market capture, fully automated
  narrative equivalence, untouched paid holdout, provider-cost measurement or
  real payment journey is claimed. QA PDFs remain private intermediate files;
  they are not new customer specimens submitted for approval.

## Next report acceptance work

Continue reconciliation of residential and commercial income, later lease
changes and security; complete original-plan and repair-recovery interpretation;
then prove the unchanged writing/rendering pipeline on the diverse acceptance
set. Existing quality gates and no-charge/refund controls remain closed/intact.
