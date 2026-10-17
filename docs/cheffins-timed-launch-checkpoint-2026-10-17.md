# Cheffins timed catalogue — 17 October 2026

## Verified implementation and source evidence

The existing collection runner now includes `collectors.cheffins_current`.
Live collection inspected all 19 advertised timed catalogue records: 15 past
results were excluded from current availability, four detail pages were checked
(including a past withdrawn residential property), and three upcoming commercial
properties were recovered for 19 November 2026:

| Property | Guide | Evidence |
| --- | ---: | --- |
| Rushmoor Garage, Tilford Road, Farnham GU10 2EP | £475,000 | https://auctions.thecpn.co.uk/lot/details/254eea64-6e3b-4843-a8ad-5dd21cebc71b |
| 9 Freer Street, Walsall WS1 1QD | £225,000 | https://auctions.thecpn.co.uk/lot/details/777d4f73-ffcd-4114-a3c2-e78b6390b715 |
| Elmsdale Social Club, Sutton Coldfield B72 1JE | £175,000 | https://auctions.thecpn.co.uk/lot/details/49d020bb-3c27-4be7-a5f3-4ae82e4540fa |

Catalogue: https://timedpropertyauctions.cheffins.co.uk/search

All three pass the existing current-property and publication checks. Prices are
the guides, not minimum opening bids. Rates payable are not treated as rent;
buyer-fee VAT is not treated as property VAT. Missing detail pages or a catalogue
denominator mismatch produce degraded collection. Explicit withdrawals are
retained; ended auctions are not inferred to remain available. No legal pack
login or document acquisition was attempted.

The timed feed is not an authoritative replacement for all Cheffins inventory:
it cannot retire records belonging to the separate rostrum catalogue. Rostrum
coverage remains unverified. Production publication remains pending the normal
collection and public-build workflow; a successful local collection is not proof
that the three records are live.

Validation: 37 focused collector, publication, withdrawal, reconciliation and
registry tests passed. Live-source collection and publication projection passed.

## Other launch evidence checked this session

The public homepage/search export shows 1,016 catalogue lots, including 49
withdrawn records; 948 available and 68 sold/withdrawn/postponed. Barrack Road
Christchurch is searchable at £575,000. These are observed snapshot counts, not
permanent expected totals.

The private Render API still serves commit
`5b5986bebcd07247637563b8545c90d528c2c6a6` despite auto-deploy being configured.
Its dashboard session requires fresh authentication before investigating the
GitHub deployment connection. Actual Watch/search email delivery is not verified.
Live billing and paid-report launch remain closed pending the existing acceptance
gates. This checkpoint does not approve report quality, payments or recovery.
