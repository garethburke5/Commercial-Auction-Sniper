# Cheffins current rostrum coverage — 17 October 2026

The existing timed collector now also follows the first-party **Current Catalogue** link. It reuses `scripts.harvest_cheffins_history.parse_catalogue` for retained-card identities, dates and denominators. It does not run the historical harvester, traverse previous catalogues or recover older sales.

The live link resolves to the completed 23 September 2026 sale:
https://www.cheffins.co.uk/property-auctions/catalogue-view,september-2026_578.htm

Fresh source collection observed:

| Feed | Advertised / read | Qualifying results |
| --- | --- | --- |
| Timed/CPN | 19 / 19 cards; four relevant detail pages | Three upcoming commercial lots for 19 November; 15 past results excluded; one withdrawn residential lot excluded by classification |
| Linked rostrum | 24 / 24 full-description cards; four commercial detail pages | Three sold commercial lots and one sold-prior garage block from 23 September |

The rostrum results are Garage and land at Pakenham Close; Garages at Debden Road; The Surgery, School Road, Kedington; and 27/28 High Street, Huntingdon. They are historical results, not extra available stock. All four detail identities and dates matched the catalogue; there were no fetch/parse failures. Existing lifecycle handling retains completed records in history.

The current classifier now recognises a former surgery when treatment-room evidence remains and no residential conversion is described, and a numbered block of single garages. Nearby amenities and converted family homes remain excluded. These are narrowly evidenced classification corrections, not a relaxation of the commercial publication gate.

The rostrum adapter retains legal-document links, first images, tenure, VAT and tenancy sections. It excludes solicitor/contact and fee boilerplate from property facts. A sale result never becomes a guide price or yield denominator. Missing details, conflicting dates, unconfirmed commercial outcomes, unexpected links or denominator gaps degrade the source rather than silently certifying an empty catalogue.

The Huntingdon source has separate totals for two buildings. These remain in the description; neither component is presented as the whole-lot floor area. The tenancy section and partial occupation are preserved. Its stated initial lease rent is source evidence, not independent verification of rent currently paid after a review. No report-quality approval follows from this collection check.

Both feeds retain separate telemetry. Headline current-candidate counts exclude completed sales; full-card parsing counts remain separate from detail-page visits. Neither feed can retire the other's records during an outage.

Validation: 884 collector tests and 19 subtests passed, including the existing Cheffins history parser regressions and new current-feed, lifecycle, identity, price, tenancy and classification cases. Hosted collection, history banking and public-build acceptance must be checked after the new code is published; the fresh local check is not proof that the new records are live. Live billing, paid-report approval and email-alert delivery remain disabled.
