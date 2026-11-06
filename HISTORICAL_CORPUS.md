# Historical auction property corpus

This collection is independent of the live-board development work. Its unit of
progress is one evidenced auction lot appearance, never an auction date alone.

## Run

```sh
pip install requests beautifulsoup4
python historical_corpus.py bank-legacy
python historical_corpus.py harvest-savills
python historical_corpus.py harvest-paul-fosh
python historical_allsop.py --workers 1
python scripts/harvest_acuitus_canonical.py --all-incomplete
python scripts/harvest_clive_emson_canonical.py --all-incomplete
python scripts/harvest_clive_emson_canonical.py --enrich-next --workers 4
python scripts/harvest_barnett_ross_canonical.py --repair-dates
python scripts/harvest_auction_house_northeast.py
python scripts/harvest_auction_house_south_yorkshire.py
python scripts/harvest_auction_house_north_west.py
python scripts/harvest_auction_house_south_west.py
python scripts/harvest_auction_house_east_anglia.py
python scripts/harvest_auction_house_national.py
python scripts/harvest_auction_house_regions.py
python scripts/harvest_bidx1_canonical.py
python scripts/harvest_btg_eddisons_catalogues.py 4
python scripts/harvest_eddisons_insights.py
python scripts/harvest_mchugh_results.py 8
python scripts/harvest_mchugh_legacy.py 8
python scripts/harvest_phillip_arnold_results.py 8
python scripts/harvest_sdl_legacy_catalogues.py --limit 10
python scripts/harvest_smith_sons_results.py
python scripts/harvest_anderson_garland_results.py
python scripts/harvest_edward_mellor_results.py --limit 24 --workers 8
python scripts/harvest_edward_mellor_pdfs.py 8
python scripts/harvest_future_property_auctions.py --limit 4 --workers 3
python scripts/harvest_town_country_results.py --workers 4
python scripts/harvest_brown_co_results.py
python scripts/harvest_bagshaws_results.py
python scripts/harvest_cottons_results.py 16 8
python scripts/harvest_harman_healy_results.py
python scripts/harvest_agents_property_auction_results.py
python scripts/harvest_first_for_auctions.py
python scripts/harvest_landwood_property_auctions.py
python scripts/harvest_sw_property_auctions.py
python scripts/harvest_eig_retained_grids.py
python scripts/harvest_eig_retained_grids.py auction-works --workers 12
python scripts/harvest_eig_retained_grids.py bradley-hall --workers 12
python scripts/harvest_eig_retained_grids.py brown-co --workers 12
python scripts/harvest_eig_retained_grids.py clarke-simpson --workers 12
python scripts/harvest_eig_retained_grids.py higgins-drysdale --workers 12
python scripts/harvest_eig_retained_grids.py property-auction-agent --workers 16
python scripts/harvest_eig_retained_grids.py lot9-auction-house --workers 16
python scripts/harvest_eig_retained_grids.py auction-north --workers 16
python scripts/harvest_eig_retained_grids.py sage-co-auctions --workers 16
python scripts/harvest_eig_retained_grids.py bowen --workers 16
python scripts/harvest_eig_retained_grids.py astleys --workers 16
python scripts/harvest_eig_retained_grids.py opal-property --workers 16
python scripts/harvest_eig_retained_grids.py newlands-property --workers 16
python scripts/harvest_eig_retained_grids.py landmark-auctions --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-11 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-10 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-03-25 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-04-15 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-05-27 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-08-19 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-11-11 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-07-29 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-05-20 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-06-24 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2025-09-30 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-01-13 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-30 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-31 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-14 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-02-24 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-17 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-03-24 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-21 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-04-28 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-09 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-05-26 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-02 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-16 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-06-23 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-07 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-14 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-21 --workers 16
python scripts/harvest_eig_retained_grids.py auction-house-online-2026-07-28 --workers 16
python scripts/harvest_propertyauctions_allsop_results.py
python scripts/harvest_lsh_results.py
python scripts/harvest_goldings_results.py
python scripts/harvest_maggs_allen_results.py
python scripts/harvest_sutton_kersh_results.py --catalogues 8 --workers 6
python scripts/harvest_knight_frank_results.py 12
python scripts/harvest_auction_estates_results.py 8
python scripts/harvest_hollis_morgan_results.py 4
python scripts/harvest_dedman_gray_results.py --workers 8
python scripts/harvest_john_francis_results.py --workers 8
python scripts/harvest_swift_property_auctions.py --workers 8
python scripts/harvest_sharpes_results.py --workers 12
python scripts/harvest_seel_catalogues.py
python historical_corpus.py build
```

The first command banks every lot already recovered in the Savills legacy
catalogue map, including residential lots. Missing street addresses remain null.
The second traverses all previously identified modern catalogue IDs and every
page, retaining the lot-level structured data embedded in the public website.
Run `harvest-savills --ids 241 --refresh` to recheck one auction.

Previously saved Savills evidence is also reconciled conservatively. The 23
January 2014 Nottingham results report contributes two numbered commercial
appearances whose missing street addresses remain null. A separately saved 22
June 2015 London catalogue supplies exact addresses for legacy AID 956 lots 34
and 126 only after date, lot, locality, property class and price checks. These
enrichments retain the original result-grid evidence and do not declare either
catalogue complete. Content-addressed source snapshots are immutable across
repeat bank runs, and later base-shard regeneration preserves additive address
evidence rather than erasing it. Two saved 2018 property records similarly
complete the unique compatible AID 1068 lot 80 and AID 1072 lot 66 addresses
after exact date, postcode-district/locality and property-class checks. The UK
postcode parser accepts valid outward-code suffixes such as ``WC1X`` and
``SW1V`` so already banked addressed rows participate in exact grouping without
changing or merging their appearance identities.

The retained PropertyAuctions result grids for Allsop Residential's 29 May,
17 July, 18 September and 31 October 2013 sales are captured separately with
their exact surviving titles and dates.  They bank all 372, 332, 255 and 232
distinct published rows respectively, rather than the lower headline
``offered`` figures.  A grid
is accepted as complete only while its single-page state, headline totals,
continuous base-lot extent and exact lettered-lot set all reconcile.  Its
locality-only rows remain partial lots with null addresses rather than
speculative address identities.

Paul Fosh collection traverses and reconciles the entire paginated public results
set, retaining all addresses, published lot end dates, outcomes, prices and detail
links. Its lot end dates are labelled as such; they are not silently assumed to
be a separate catalogue's date. Listing UUIDs preserve stable source identity.
Each run reports new address and partial records separately, reconciles the
current public denominator and retains earlier UUIDs that have fallen out of the
live pagination instead of silently deleting historical appearances.

Allsop collection traverses the first-party past-auction manifest and each
catalogue's paginated public search results, prioritising commercial catalogues
while retaining residential lots. Stable auction/lot UUIDs preserve repeat
appearances. Explicit test rows, lot-zero dividers and future auctions are not
admitted; raw page snapshots and per-auction count reconciliation are saved.

Acuitus collection uses the first-party results selector and requests the full
published card set rather than the site's 128-row default. It resumes only years
with a newly discovered or unreconciled sale, while an explicit `--year` remains
available for a source refresh. Earliest broken generic property links retain the
auction-date-plus-lot identity and archive evidence instead of inventing an ID.

Clive Emson collection traverses the first-party results index and banks every
distinct surviving lot card in each unpaginated catalogue. The official archive
also exposes a lot-numbering extent; missing numbers are recorded as gaps, not
manufactured appearances. Card localities remain separate from street addresses
pending detail-page enrichment. The resumable detail pass revisits one oldest
partial catalogue at a time, preserves each raw lot page, and upgrades only the
same immutable appearance ID after the page's auction date and lot number agree.

Barnett Ross collection traverses the first-party past-results index back to
November 2002 and banks every visible UK result row, including residential and
lettered lots. Modern property IDs, intermediate PDF paths, and the earliest
catalogues' exact auction-plus-lot numbers provide stable appearance identity.
Linkless legacy rows keep property_id null and are never merged across auctions.
Exact days in first-party archive URLs take precedence over page chrome. Month-only
catalogues accept body dates only when adjacent to the archive month; otherwise
auction_date stays null so the sitewide next-auction banner cannot contaminate
historical appearances. --repair-dates revisits only states with implausible legacy
dates or newly discovered catalogues, and marks checked states to prevent zero-row
re-probes.
Each unpaginated catalogue is complete only when every visible row reconciles to
one distinct evidenced identity; Spain-only sales are explicitly excluded.

Auction House North East collection traverses every retained page of the
first-party online-results table. Stable redirect IDs preserve identity, exact
lot-end timestamps are labelled as such, and sold, sold-prior, last-bid and
postponed states are not conflated. Full addresses, guides, results and immutable
page snapshots are retained. Pagination can be complete while original auction
catalogues remain explicitly unreconciled when their denominators are absent.

Auction House South Yorkshire uses the same evidenced row model across its much
deeper retained archive. Every paginated online result is banked independently,
including repeated property appearances, no-bid and withdrawn states. Complete
archive pagination is reported separately from unavailable original catalogue
denominators, so catalogues are not falsely marked complete.

Auction House North West, South West and East Anglia use the same strict model:
every retained page is captured, stable redirect IDs prevent speculative merges,
and exact lot-end timestamps remain distinct from original catalogue dates.
Regional archive pagination is reconciled independently while unavailable
catalogue denominators keep those original catalogues explicitly incomplete.

The Auction House National results archive is an aggregator, not a separate
auctioneer. Its collector attributes each row to the published regional
auctioneer, merges only previously unseen stable redirect IDs into that region's
canonical shard, and defers Auction House London rows until they can be
crosswalked safely to the existing catalogue corpus. This avoids inflating the
database with the same appearance from overlapping regional and national pages.

The dedicated regional recovery pass revisits Wales, Notts & Derby, Cheshire,
Staffordshire & Shropshire, Birmingham & Black Country, Kent, West Yorkshire,
Lincolnshire/North Notts/South Yorks, Hull & East Yorkshire, Coventry &
Warwickshire, Manchester, North Yorkshire & Tees Valley, Cumbria, Sussex &
Hampshire, Essex, Leicestershire, Scotland, Northants/Bedfordshire/Buckinghamshire,
Chesterfield & North Derbyshire and Northern Ireland. These archives can retain
rows outside the National view. Exact regional auctioneer plus redirect ID reuses
the canonical appearance identity, preserves earlier evidence unchanged, and
admits only IDs not already banked. Pagination completeness remains separate
from unavailable original catalogue denominators.

BidX1 collection begins from independently evidenced, auction-ID-specific UK
result sets. A catalogue is complete only when its published result count,
stable property links and successfully parsed detail pages agree exactly. Each
property's own closing timestamp supplies the appearance date; the collector
does not infer dates from a search container. Residential and commercial lots
are retained together, with raw index and detail snapshots preserved.

BTG Eddisons catalogue collection traverses both pages of the first-party
previous-results archive and every page of each retained live-stream and online
catalogue. Every visible property card is preserved. A catalogue is complete
only when distinct first-party property identities and captured pages reconcile
exactly to its published ``results found`` denominator. Online appearances use
the published closing day; lots in two-day live-stream catalogues keep a null
individual auction date while preserving the exact published date range.

BTG Eddisons' retained monthly sold-result articles are collected separately
from complete catalogues. Every published property block is preserved, but the
records remain explicitly partial because the articles contain selected sold
examples and publish a month rather than an exact auction day.

McHugh & Co collection preserves both the current first-party results archive
and the older retained auction-table site. The modern pass records every visible
property card and keeps catalogue completeness false whenever the published
offered count disagrees with the source rows. The legacy pass reconciles each
unpaginated table independently and scopes stable identities to its exact
auction date, retaining residential, commercial and land lots together.

Phillip Arnold collection traverses every retained first-party result table and
banks all visible lot rows, including withdrawn and reoffered properties. Stable
detail identities and exact auction dates preserve repeat appearances. Published
offered totals are kept as evidence; any disagreement with the visible row count
keeps the catalogue incomplete rather than discarding or inventing lots.

SDL Property Auctions collection traverses the retained first-party catalogue
archive from May 2022 through November 2025, before the BTG-era Eddisons
collector begins. Only featured cards with an exact catalogue date, stable SDL
property ID, lot number, postcode-bearing address and guide price are admitted.
Raw archive and catalogue HTML are preserved. These surviving featured subsets
never count as complete auctions because their original catalogue denominators
and non-featured rows are no longer exposed.

Smith & Sons collection follows the current first-party past-auctions index and
explicitly recovered older catalogue identities whose result pages remain
public. Because the catalogue defaults to 20 cards, the collector requests its
50-row view and marks a sale complete only when all captured cards and stable
per-property identities reconcile exactly to the explicit result denominator.
Source-repeated displayed lot labels are reported rather than rewritten.
Complete snapshots are reparsed locally instead of repeatedly fetched.
Residential, commercial and land rows, repeated property appearances, guide
ranges, outcomes and sale prices are preserved with immutable page snapshots.

Anderson & Garland collection preserves every sold-property block on its
first-party recent-results page, including address text, description, image,
guide and sale price. The page is curated rather than a dated catalogue: exact
auction dates remain null and the records are explicitly excluded from complete
catalogue counts. Rex listing IDs provide identity where retained; otherwise an
exact source-heading hash is used without merging across other auctioneers.

Edward Mellor collection discovers retained first-party result pages from the
auction archive and resumes through up to 24 previously uncaptured catalogues
per run. Every visible card is preserved by exact auction slug, lot number and
stable property ID. Retained detail pages may add the full address, tenure,
images and the exact lot-level auction date only when the property ID and lot
number reconcile. Two-day headings remain a date range rather than an invented
lot date, and catalogues remain incomplete when the original offered
denominator is unpublished.

Edward Mellor's separate legacy-PDF pass resumes oldest-first through the
first-party result sheets retained from 2010 onward. It preserves every printed
lot row, exact auction date, address text, outcome and published sold or
available price. Exact result-sheet URL plus date and lot number keeps these
appearances separate from modern cards. A sheet is complete only when its
distinct printed labels include a continuous base-lot sequence; lettered lots
remain independent additional appearances. Raw PDFs and the archive page are
saved as immutable provenance.

Seel & Co collection banks 17 complete first-party catalogue PDFs retained from
December 2019 through April 2022. Every printed residential, commercial and
land row is preserved using the exact catalogue date plus lot number, together
with its address, guide or published outcome and immutable raw PDF. A catalogue
is complete only when its order-of-sale table or numbered detail pages reconcile
exactly to a contiguous published 1..N denominator. The October 2021 catalogue
is recovered from all 36 numbered detail pages; four pages use OCR where the
PDF's native text is absent or corrupt, and one confidential lot remains an
explicit partial lot rather than receiving a speculative address.

Town & Country Property Auctions collection traverses all pages of the
first-party past-auctions archive. Stable lot UUIDs and exact closing timestamps
preserve each appearance independently across the auctioneer's regional offices;
addresses, outcomes, prices, descriptions and images are retained without
collecting bidder or registrant data. Archive pagination is reconciled separately
from unavailable original catalogue denominators, so no inferred grouping is
marked as a complete auction. After one reconciled full pass, later runs fetch
only page one unless a new UUID or changed page extent requires another full
traversal.

Brown&Co collection preserves every result card currently retained on the
first-party property-and-land results page. Stable public EIG lot IDs keep each
appearance independent, including genuine lot-zero properties; exact published
start and end dates, addresses, outcomes, prices and images are retained. The
page is rolling and publishes no archive denominator, so earlier saved rows are
merged rather than removed and no original catalogue is marked complete.

Bagshaws collection traverses the first-party dated property-auction archive and
banks explicit property cards plus tabular result rows. Stable property URLs are
scoped to the auction page so repeat appearances remain separate. Result rows
enrich a card only on an exact normalized title, or an exact lot marker plus
contained title tokens; unmatched results retain their own exact heading hash.
Pages exposing narrative only create no synthetic lots, and no auction is marked
complete because the original catalogue denominator is unavailable. Subsequent
runs skip previously checked pages unless `--refresh` is requested.

Cottons collection follows the first-party auction archive's dated result PDFs,
which survive from 2001 onward. Each bounded run resumes with the newest incomplete
sheets, corroborates the archive date against the PDF heading, and preserves every
published lot row, address, outcome and result or available price. Exact auction
date plus printed lot number provides appearance identity. A sheet is complete
only when its distinct published lot labels and continuous base lot sequence
reconcile; lettered additional lots remain separate rows. Raw archive HTML and
compressed source PDFs are retained for provenance. Image-only PDFs are OCRed
from those saved snapshots in bounded groups of eight. The OCR pass uses
300-dpi lossless rasterisation, table-aware page segmentation and versions its
parsing rules, so a materially
improved parser may revisit an earlier quarantine once while unchanged failures
are not probed repeatedly.

Future Property Auctions collection consumes the auctioneer's unauthenticated
first-party BidJS archive. The manifest currently retains stable auction UUIDs
back to September 2019; each selected auction is marked complete only when its
listing, sale and status maps contain the same distinct listing UUIDs. Collection
is deliberately bounded and resumable, newest first. Address-bearing titles,
descriptions, property IDs, images, lot numbers, exact closing dates and public
outcomes are preserved across residential, commercial and land lots. Sold prices
come only from the public highest bid for a source-marked sold lot; unsuccessful
bids are not mislabelled as results. Sanitized immutable snapshots omit
registrants, bidder/user identifiers, full bid histories and unpublished reserve
values while retaining the response hash and all fields used by the collector.

Harman Healy collection traverses the complete first-party retained
past-auctions grid. Every address-bearing lot card is preserved, including
residential, commercial, mixed-use and land appearances, using the source's
stable EIG lot identity and the published individual lot end date. The archive
is marked complete only when all pages, distinct identities and the explicit
published lot denominator reconcile exactly. Immutable page snapshots preserve
the result text, property summary and images. Once complete, later runs fetch
the archive head and reuse unchanged full-page snapshots; an increased
denominator re-fetches the previous partial tail and every newly added page.

LSH Auctions collection traverses the complete first-party retained
past-auctions grid. It preserves every address-bearing residential, commercial,
mixed-use and land row under the source's stable EIG lot UUID, including sold,
sale-agreed, sold-prior, withdrawn, postponed and unsold outcomes. The archive
is marked complete only after its explicit lot denominator, every page and every
distinct identity reconcile. Because this grid is newest-first, saved pages are
reused only while the denominator is unchanged; any count change triggers a full
pagination refresh so shifted page boundaries cannot omit or duplicate lots.

Goldings Auctions collection traverses the first-party dated result archive and
preserves every surviving address-bearing lot card back to December 2015. Each
sale's published lots-offered figure is retained as its denominator. A catalogue
is complete only when distinct source lot IDs reconcile exactly to that figure;
catalogues with removed or additional retained cards remain explicitly
incomplete while every visible residential, commercial, mixed-use and land
appearance is still banked. Immutable archive and catalogue snapshots preserve
the source result text, prices, property type, description and images.

Maggs & Allen collection preserves every distinct property row in the
first-party retained sold-results selection. Stable source property IDs, full
addresses, guide and sold prices, descriptions and images are retained. Detail
pages supply exact auction dates only when their narrative agrees with the
index's published month; conflicts remain null and are reported. The unpaginated
``n=0`` index is reconciled independently, while every reconstructed auction
group remains incomplete because the source publishes neither the original
catalogue denominator nor every historic catalogue row.

Sutton Kersh's first-party dated results archive is fully banked: 11,401
appearances across all 107 retained periods back to May 2011. Every row keeps
its exact auction date, published lot number, stable period/property identity,
address, outcome, price, description, image and legal pack link where exposed.
Each catalogue is complete only because every 48-row page and distinct property
identity reconciles exactly to the source's published property denominator.
Completed immutable pages are reused on later runs, making refreshes idempotent
unless the first-party archive adds or changes a published period.

Knight Frank Auctions collection reconciles every card in the first-party
recently-sold page against its explicit source-row count, then enriches each
stable EIG property identity from its retained detail page. Exact auction dates,
lot numbers, property types, tenure, occupancy, results, prices, images and legal
pack links are preserved where published. The source calls this a selection of
recent sales, so its retained grid can be source-row complete while the original
auction catalogues remain explicitly incomplete. Repeated identical card
presentations are preserved in the raw snapshot but do not inflate appearances.

Auction Estates collection traverses every dated option in the first-party
results selector back to December 2016. Each unpaginated catalogue is marked
complete only when its visible property cards and distinct appearance identities
reconcile to the catalogue's own published result denominator. All property
types and outcomes are retained with immutable page snapshots; repeat property
IDs on different auction dates remain separate appearances.

Hollis Morgan collection banks the 33 retained first-party result catalogues
from September 2010 through November 2015. Later catalogues preserve exact
printed dates, addresses, guide prices, outcomes, sold prices and stable
property IDs. Pre-URL catalogues use exact printed lot labels and PDF source
positions for appearance identity; because their extracted columns interleave
property and solicitor details, address and postcode remain null rather than
being guessed. Shared-page lots are separate partial records. Ordered per-page
text snapshots and binary hashes preserve the evidence. All surviving source
rows are banked, while original catalogues remain explicitly incomplete where
their offered denominator or one-to-one row mapping cannot be reconciled.

Dedman Gray collection traverses the first-party retained EIG results archive
back to February 2013. Every unpaginated catalogue row is preserved with its
stable source lot ID, exact archive date, lot number, address, postcode,
description, image, outcome and published result price. Residential,
commercial, mixed-use and land lots are retained. A catalogue is complete only
when every visible row has a distinct appearance identity and its published
heading day and month reconcile with the archive date.

John Francis collection traverses every retained first-party auction lot list
back to September 2013. Each unpaginated list is preserved with its exact
archive date, venue, stable EIG lot ID, lot number, address, postcode, result
and published sale price. All property types and repeat appearances are kept.
A catalogue is complete only when every distinct visible lot ID is represented
once and the lot-list heading date agrees exactly with the archive date.

Swift Property Auctions collection traverses the complete first-party results
archive and banks every property card from each unpaginated catalogue. Stable
property IDs are scoped to the published auction ID so repeat appearances remain
separate. Exact archive dates, result-page headings, visible cards and published
lot denominators must all reconcile before a catalogue is complete. Addresses,
descriptions, guides, outcomes, prices, legal-pack links, images and raw page
snapshots are retained without filtering residential or unknown-sector lots.

Sharpes Auctions collection traverses every dated catalogue in both first-party
traditional- and modern-auction results archives. Each unpaginated page is banked with its
stable property route ID, exact auction date, lot number, address, postcode,
guide, outcome, published sold price and image. Repeat appearances are scoped to
their auction date and auction type. A catalogue is complete only when every visible property
card has one distinct identity and the page heading agrees with the archive URL
and link date; malformed or duplicated cards keep it incomplete.

Cheffins collection reconciles its first-party result archive's published lot
denominator against every retained card and catalogue-linked addendum. Where an
older page has dropped a card, an identity-only partial row is banked only when
the surviving lot numbers are unique integers in the published 1..N sequence
and therefore prove the exact missing lot number. Address, property type,
outcome and price remain null, zero-card or lettered sequences are not inferred,
and a gap row never makes the catalogue complete.

Pugh's retained first-party property-search archive is captured as a canonical
appearance source across residential, commercial, mixed-use and land rows. The
first pass reconciles every published result page and banks property IDs,
addresses, auction dates, lot numbers, descriptions, guide/result prices and
outcomes with immutable HTML snapshots. Incomplete follow-ups fetch only missing
or failed pages; complete runs stop after a full page of previously observed
appearances. A stable property URL is property identity rather than appearance
identity: the collector retains repeated URLs when exact auction date or lot
differs. Conflicting duplicate presentations of the same property/date/lot are
preserved as alternate raw rows in provenance rather than inflating appearance
counts. Two earlier Pugh research records are merged only on exact normalized
address, matching lot number and a single auction date within fourteen days;
otherwise repeated appearances remain separate. Archive completeness requires
every page and the sum of page-row counts to reconcile to the published archive
total. Original auction denominators remain unavailable, so this never falsely
marks individual auction catalogues complete.

Pugh's deepest all-types list pages currently return HTTP 500. The collector
uses the site's first-party 80-card view only after an exact 60-row source-ID
overlap with the preceding working list pages, allowing all published source
positions to be reconciled without repeating the failed probes. Cards that lack
an auction date and lot number are retained with immutable snapshots under
`data/auction_history/sources/pugh/`; they are deliberately excluded from the
appearance database and its headline totals until another first-party source
can establish an auction appearance. A strict detail-page recovery pass now
revisits those saved tail rows and promotes a row only when the retained page's
property identity, exact normalized address, auction date and lot number all
reconcile; failed or ambiguous rows remain excluded. Detail URLs returning a
confirmed HTTP 404, or surviving pages that expose neither an exact lot number
nor auction date, are quarantined as source blockers and are not repeatedly
probed or counted as separate catalogue failures. The Pugh state reports
source-row reconciliation and appearance completeness separately.

`data/auction_history/progress.json` is the counted output of the rebuilt
database, not a discovery counter. All legacy source rows are kept, including
those outside the London/National archive date list. Auction IDs prevent same-day
catalogues from being collapsed.

## Records and evidence

- `appearances/`: one compressed JSONL shard per auction. Repeated appearances
  remain separate. A later fetch does not silently remove a previously saved lot.
- `sources/`: public lot payload snapshots or the precise earlier legacy grid
  snapshot, with retrieval/source URL, capture time and content hash. Account,
  vendor, bidder, buyer and solicitor identifiers are not collected.
- `auctions/`: per-catalogue traversal/count reconciliation, exclusions and errors.
- `auction_history.sqlite.gz`: compressed database, rebuilt from the shards.

The SQLite database contains `appearances`, `properties`, and `auctions` tables.
All the recovered fields are also available in each appearance's `record_json`.
An integration can query postcode or source ID, show a property timeline using
`property_id`, and keep the evidence link next to each observation. Exact address
groups are conservative candidates, not verified UPRNs or building counts. A lot
can contain multiple physical properties; this version does not split such lots.

```sql
SELECT auctioneer, auction_date, lot_number, guide_price, sale_price, original_url
FROM appearances WHERE property_id = ? ORDER BY auction_date;
```

## Counting rules

Lot zero/section adverts are excluded. Date and source lot identity must agree
with the fetched catalogue. All pages must be traversed, source IDs must be
distinct, and the total must reconcile with the published category counts before
a modern catalogue is marked complete. This is completeness of the surviving
online catalogue; it does not prove that deleted original lots were recovered.

Legacy partial lots have date, source auction ID, lot number, locality, type and
result where these survived. When the saved result-grid location itself contains
an explicit numbered premise, that text is also retained verbatim as the address;
towns, districts and unnumbered roads are not promoted or guessed. The remaining
rows are real partial lot records, not full-address properties. Their auctions
remain unreconciled until original completeness can be established. An unavailable
source or a failed parser is a failure, never zero properties successfully harvested.

Saved source-corpus shards may also enrich one exact appearance by its immutable
appearance ID. Enrichment fills a missing address only, rejects conflicting text,
and appends the source snapshot and hash without replacing the lot's original
result-grid evidence. It does not create a duplicate appearance or imply catalogue
completeness.

The older `data/property_history.json` has known date, classification and matching
issues. It remains intact. Do not add its count to this corpus: it overlaps with
this collection and must be reconciled source by source before import.

## Continuation

20 October: the owner resumed archive work. Scheduled runs now rotate through 50 existing archive tasks, running four
tasks per batch, each capped at five minutes, recording failures/timeouts separately
from captured-lot counts. `continuation_collection.json` preserves the next task.
Explicit `all` and `retained-legacy` dispatches remain available for broader work.
The rebuilt database is also committed in checksum-verified parts under
`database_parts/`; the website prefers that manifest over the older single gzip.
This prevents the single-file size limit leaving the site on a stale database
while newer progress totals are published. Source shards remain the durable
evidence and can rebuild the database. Current commercial-board scope is separate
from the all-property historical corpus.

The Historical lot corpus collection workflow resumes incomplete known Savills
catalogues every six hours and saves checkpoints to the repository. Its separate
output paths avoid collisions with live-board scans. Modern completed auctions
can be refreshed explicitly. The broader operation must next recover missing
legacy street addresses, revisit missing years/sources, import and validate other
auctioneers' existing raw lots, and add adapters for all recoverable UK sources.
The operation is not complete merely because currently known URLs are exhausted.

Auction Hammer Midlands is collected from its first-party WordPress property
archive with stable WordPress property identities. Older pages explicitly
branded Auction House Staffordshire remain under the reconciled operator label
and carry `historical_trading_name`; that predecessor name is not counted as a
second auctioneer. Property-page dates must reconcile to a dated first-party
auction post, and the surviving-property set is not claimed as an original
catalogue denominator.

The shared EIG retained-grid collector also covers The Auction Company's
official auction platform. It reconciles the complete visible pagination,
requires distinct stable EIG lot UUIDs, snapshots every grid and detail page,
and preserves individual dates, guides, achieved prices, rents and outcomes.
The completion scope is the surviving first-party grid only; it does not imply
that deleted earlier lots have been recovered. Auction Local's related official
site currently exposes zero rows in its past-properties grid, so that route is
recorded as blocked rather than counted as a zero-lot collection.

Loveitts' separate first-party archive can be collected with:

```bash
python -u scripts/harvest_loveitts_archive.py --workers 20
```

It reconciles every retained property card in all linked event pages from the
dated archive index, then enriches only property pages whose published event
date exactly matches that appearance. Guide ranges and achieved prices remain
separate, while sold-prior/sold-after/withdrawn/unsold states and rents are
preserved where published. Exact date/address overlaps already banked from the
shared Auction House platform are recorded and excluded from growth. Loveitts
Limited (company 07558151), its Loveitts trading name, and the linked Auction
House Coventry & Warwickshire platform are not counted as three auctioneers.
The completion claim covers surviving cards only; unlinked index dates and
properties removed from historic pages remain outside it.

Butters John Bee's paired catalogue and result archive can be collected with:

```bash
python -u scripts/harvest_butters_john_bee_archive.py --workers 12
```

Each result PDF must expose a complete sequential lot table before admission.
The paired catalogue independently supplies the exact event date and can enrich
the same printed lot with property type, tenure and rent. Result PDF bytes and
catalogue extracted text are retained as immutable evidence with the original
PDF URLs and source SHA-256 values. Exact date/address overlaps across the
existing corpus are audited and excluded. Butters John Bee Limited (company
05289439), its lower-case trading style, its branches and the related Darlows,
Haybrook and haart group brands are not counted as additional Butters John Bee
auctioneers. Coverage is limited to the catalogue/result pairs still published
on the first-party archive; no pre-2024 completeness claim is made.

Purplebricks' first-party GOTO retained grid can be collected with:

```bash
python -u scripts/harvest_purplebricks_online_auctions.py
```

This wrapper reuses the reconciled EIG/GOTO grid collector but targets the
platform's `/search` archive rather than `/past-auctions`. Every page must
carry the same published denominator and every card must retain a distinct
source lot identity, individual end date and address before the archive is
banked. Published sold-prior, sold-after, no-bid, withdrawn and postponed
states remain distinct, and monetary result text is treated as an achieved
price only when the source labels it as a sale outcome. Undated `Committed
Offer` property cards are reconciled against the published denominator but
retained as audited non-auction exclusions rather than manufactured auction
appearances. Stable EIG lot IDs already retained by another white-label source
are recorded as duplicate-source exclusions; address similarity alone never
collapses potentially different legal interests. Purplebricks is the branded
channel and Genle Limited trading as
GOTO Group (company 09790404) is the platform operator; both directory names
map to the single `Purplebricks Online Auctions` corpus label and are not
counted as separate auctioneers.

Edward Mellor's bounded PDF pass retains definitive 404/410 result links as
terminal source blockers in its collection summary. A missing source is never
counted complete, but it no longer consumes a harvest slot on every run while
later first-party result sheets remain usable. Transient download and parser
failures still fail the pass. Successfully banked sheets with non-contiguous
published numbering remain explicitly incomplete and are not downloaded again.

The target is every UK auctioneer's individual lots over the preceding 20 years,
with guide ranges, reported sale prices, outcomes and original evidence wherever
available. Older recovered records are retained. `progress.json` now includes
`twenty_year_coverage`: populated price fields and sold-without-price counts by
auctioneer/year, with unknown and future dates separated. Missing years and
missing prices do not imply zero auctions or a zero sale price. These counts
measure stored evidence, not verified national completeness.

## Latest persisted collection handoff — 5 November 2026

The retained Bagshaws Bakewell page dated 17 November 2025 has been banked
from its immutable first-party HTML snapshot. Fourteen individually named sold
interests were added: twelve with achieved prices and two sold prior with prices
left null. The page's aggregate says fifteen lots sold, so the one unnamed
interest was excluded. The event remains incomplete and national completeness
remains false.

Net gain: 14 appearances, 14 address records, 14 exact-dated records inside the
preceding 20-year window, 12 achieved prices, no guides, no rents, no
commercial/mixed-use rows, no partials, no undated or future-dated rows, and no
duplicate appearance identities. Sector deltas were three land, four residential
and seven unknown. The rebuilt corpus totals are 310,121 appearances, 299,169
address records, 301,860 in-window appearances, 104,815 in-window guides and
112,018 in-window achieved prices. Bagshaws now has 250 appearances.

Collection release: `96213aaab75e941ccb07f7fc6ceb99871ad6d965`.
The first attempt was blocked before collection by unrelated PDF/OCR setup and
banked no growth at `7251ef984d66fe6dd68826e286db97be97bb0ff2`.
The reusable workflow correction is
`b908fa04b1f6025160471e8d488400843cb2b097`; successful collection run
`42055035885`, banked evidence
`26df56ea198b35a96c59e86068ac5fa629e53e3a`, verified publication run
`42055901715`.

Next concrete growth target: reparse the retained Bagshaws Bakewell page dated
21 July 2025 and bank its nine individually priced property outcomes: three
pre-auction sales (Wharf Bungalow, Land at Merehay and Land at The Wash), New
Barn Farm at Aldwark, and the five other named sales. Preserve pre-auction status
separately, keep every achieved price distinct from guide evidence, exclude
unidentified or ambiguous catalogue interests, reconcile exact-event overlaps,
and leave the inventory incomplete unless every original lot can be named.
This newer handoff supersedes older Bagshaws target text in
`continuation_collection.json`.

## Latest persisted collection handoff — 5 November 2026 (Bagshaws July 2025)

The retained Bagshaws Bakewell page dated 21 July 2025 has been reparsed from
its immutable first-party HTML snapshot. Nine individually named property
outcomes were added: three pre-auction sales with their achieved prices and six
auction sales with achieved prices. The pre-auction statuses remain distinct
from auction-room sales. Unidentified, under-offer and merely available
interests were excluded; previously banked page-card evidence was preserved.
The event remains incomplete and national completeness remains false.

Net gain: 9 appearances, 9 address records and 9 exact-dated records inside the
preceding 20-year window. Five are land, one residential and three unknown;
none are commercial or mixed-use. The gain contains 9 achieved prices, no guide
prices and no rents, with no new partial, undated, future-dated or duplicate
result identities. No new source-year was opened because Bagshaws 2025 evidence
was already present. The rebuilt corpus totals are 310,130 appearances, 299,178
address records, 301,869 in-window appearances, 104,815 in-window guides and
112,027 in-window achieved prices. Bagshaws now has 259 appearances.

Collection release: `ea36962f2c8cb420d9da433a773905499dbfe113`;
successful collection and rebuild run `42061439454`; banked evidence
`bfaaa0ff870a440b7a838c4b3ba9b5f495502e02`; verified GitHub Pages and
auctiongeek.co.uk publication run `42062195284`. The separate publication
revalidation checkpoint `42061439909` was preserved as failed: its live-source
validation found rich-particular coverage of 50% for Auction House Cumbria and
Auction House National Online against a 60% threshold. It reclassified no fresh
lots and was not rerun; this blocker is outside the saved historical result
inventory collected here.

Next concrete growth target: reparse the retained Bagshaws Bakewell page dated
18 May 2026 (`bagshaws-may-land-property-auction-bakewell`) and bank its complete
eight-row published result list: five named achieved-price sales and three named
no-sales. Keep the two Dobbin Lane legal interests separate as Lots A and B,
preserve the three no-sale outcomes with null sale prices, reconcile any exact
page-card overlap, and leave national completeness false. This handoff
supersedes older Bagshaws targets in `continuation_collection.json` and earlier
sections of this file.

## Latest persisted collection handoff — 5 November 2026 (Bagshaws May 2026)

The retained Bagshaws Bakewell page dated 18 May 2026 has been reparsed from
its immutable first-party HTML snapshot. Its complete eight-row published
result list now reconciles five achieved-price sales and three named no-sales.
Seven rows are net-new appearances. The eighth, Lot 3 Land and Stables at The
Lodge, Tideswell, exactly matches an existing first-party property card; that
appearance retained its £100,000 guide and gained the published lot number and
no-sale outcome instead of being counted twice. Dobbin Lane Lots A and B remain
separate legal interests under published source Lots 5 and 6.

Net gain: 7 appearances, 7 address records and 7 exact-dated records inside the
preceding 20-year window. Five are land and two unknown; none are commercial or
mixed-use. The gain contains 5 achieved prices, no new guides and no rents, with
no new partial, undated, future-dated or duplicate identities. One exact
page-card overlap was enriched but excluded from appearance growth. No new
source-year was opened because Bagshaws 2026 evidence was already present. The
rebuilt corpus totals are 310,137 appearances, 299,185 address records, 301,876
in-window appearances, 104,815 in-window guides and 112,032 in-window achieved
prices. Bagshaws now has 266 appearances. National completeness remains false.

Collection release: `1757d1f7c6904a0d3f8a51a79e03a58b6ed02e4a`;
successful collection and rebuild run `42070387530`; banked evidence
`b8c0632d6a76ce7307eac28d511b5a747c67f949`. Publication run
`42071274657` preserved its first-attempt GitHub Pages deployment failure
(`Deployment failed, try again later`) and succeeded on a failed-job-only retry
from the same banked revision, including auctiongeek.co.uk. Separate revalidation
run `42070387612` was preserved as failed after reclassifying 0 fresh lots:
Auction House Cumbria and Auction House National Online remain at 50% rich-
particular coverage against the 60% threshold. It did not affect historical
collection or publication.

Next concrete growth target: reparse the retained Bagshaws Bakewell page dated
19 May 2025 (`bakewell-land-property-auction-in-may`) and bank its 13 separable
named outcomes: six sales with achieved prices, two sold-prior outcomes, one
sold-after outcome and four unsold interests. Keep Land at Fenny Bentley Lots A
and B separate, keep every unknown price null, reconcile exact-event overlaps
and preserve the existing saved snapshot. This handoff supersedes older
Bagshaws target text in `continuation_collection.json` and earlier sections of
this file.



## Latest persisted collection handoff — 5 November 2026 (Bagshaws May 2025)

The retained Bagshaws Bakewell page dated 19 May 2025 has been reparsed from
its immutable first-party HTML snapshot. Thirteen individually named outcomes
were added: six sales with achieved prices, two sold-prior outcomes, one
sold-after outcome and four unsold interests. Bowling Green Farm Lots A and B
and Land at Fenny Bentley Lots A and B remain distinct legal interests. Every
non-priced outcome retains a null sale price. The previously banked navigation-
derived page card was preserved rather than discarded, but is excluded from
this run's growth. The source does not publish a complete original catalogue
denominator, so the event remains incomplete and national completeness remains
false.

Net gain: 13 appearances, 13 address records and 13 exact-dated records inside
the preceding 20-year window. Nine are land and four unknown; none are
commercial or mixed-use. The gain contains 6 achieved prices, no guide prices
and no rents, with no new partial, undated, future-dated or duplicate result
identities. No new source-year was opened because Bagshaws 2025 evidence was
already present. The rebuilt corpus totals are 310,150 appearances, 299,198
address records, 301,889 in-window appearances, 104,815 in-window guides and
112,038 in-window achieved prices. Bagshaws now has 279 appearances.

Collection release: `1b4654e684b4d784c9156081a39e50085307231d`;
successful collection and rebuild run `42081577868`; banked evidence
`cc1666b567a3cbd68a7110cc2546879f4595301e`; verified GitHub Pages and
auctiongeek.co.uk publication run `42082542540`. Separate live-snapshot
revalidation run `42081577877` timed out while still in checkout and was
preserved as cancelled without collecting, writing or publishing; it was not
rerun.

Next concrete growth target: reparse the retained Bagshaws Bakewell page dated
20 September 2021 (`bakewell-property-auction-september-2021`) and bank its
nine individually named interests: seven sold lots with achieved prices, Lot 8
Brookfield Grove as unsold and Lot 9 Westhaven/The Beeches as postponed. Keep
Lots 4 and 5 at Alabaster Lane separate, ignore every per-acre comparison,
preserve unknown guide and rent values as null, reconcile exact-event overlaps,
and leave the event incomplete unless its original denominator reconciles.
This handoff supersedes older Bagshaws target text in
`continuation_collection.json` and earlier sections of this file.


## Latest persisted collection handoff — 5 November 2026 (Bagshaws September 2021)

The retained Bagshaws Bakewell page dated 20 September 2021 has been reparsed
from its immutable first-party HTML snapshot. Nine individually named interests
were added: seven sold lots with achieved prices, Lot 8 Brookfield Grove as
unsold and Lot 9 Westhaven/The Beeches as postponed. Alabaster Lane Lots 4 and
5 remain separate legal interests. The published per-acre comparisons were
excluded from achieved-price fields, and the two non-priced outcomes retain
null sale prices. The previously banked navigation-derived page card was
preserved rather than discarded, but is excluded from this run's growth. The
page's stated denominator conflicts with its later numbered postponed interest,
so catalogue completeness remains false and national completeness remains
false.

Net gain: 9 appearances, 9 address records and 9 exact-dated records inside the
preceding 20-year window. Four are land and five unknown; none are commercial
or mixed-use. The gain contains 7 achieved prices, no guide prices and no rents,
with no new partial, undated, future-dated or duplicate result identities. No
new source-year was opened because Bagshaws 2021 evidence was already present.
The rebuilt corpus totals are 310,159 appearances, 299,207 address records,
301,898 in-window appearances, 104,815 in-window guides and 112,045 in-window
achieved prices. Bagshaws now has 288 appearances.

Collection release: `29e41cb404e625e82444418be7611f526578a8b3`;
successful collection and rebuild run `42090729565`; banked evidence
`d3b726ed89913e2c6f4a81413556ba05a0a89862`; verified GitHub Pages and
auctiongeek.co.uk publication run `42091818524`. Separate live-snapshot
revalidation run `42090729601` reclassified 0 fresh lots and failed at the
preserved publication threshold: Auction House Cumbria and Auction House
National Online remain at 50% rich-particular coverage against 60%. It wrote
and published nothing and was not rerun.

Next concrete growth target: reparse the retained Bagshaws Bakewell page dated
22 September 2025 (`bakewell-land-property-auction-in-september`) and bank
its ten individually named appearances: six sales with achieved prices,
Hollyseat Cottage as sold prior with a null price, and the three named available
properties Long Lane Head Barn, Pethills Head Farm and 47 Chesterfield Road.
The page only says those three did not sell or were postponed, so preserve that
published ambiguity and do not assign unsupported individual statuses. Exclude
the £1.85 million aggregate, reconcile exact-event overlaps, preserve the saved
snapshot and leave the event incomplete. This handoff supersedes older Bagshaws
target text in `continuation_collection.json` and earlier sections of this
file.

## Prepared collection handoff — 5 November 2026 (Bagshaws September 2025)

The reusable saved-narrative importer now supports a verbatim published result
text that is distinct from the normalized status. This is required by the
retained 22 September 2025 Bagshaws page: it collectively says that Long Lane
Head Barn, Pethills Head Farm and 47 Chesterfield Road "did not sell or were
postponed and remain available", without identifying which outcome applies to
which property. The checked inventory therefore keeps each row's status as
unknown, its sale price null and the source wording intact. Six separately
priced sales and Hollyseat Cottage sold prior are also transcribed; the £1.85m
aggregate is excluded. Tests pass 124/124.

A saved-snapshot dry run produced ten candidate address appearances, all dated
22 September 2025 and inside the twenty-year window: two land and eight unknown,
with six achieved prices, no guides, no rents, no commercial or mixed-use rows,
and no partial, undated, future-dated or duplicate result identities. These are
candidate metrics only and are not claimed as banked growth. Release
`ef5696415bea0430ea0d5ee0cf07043884542337` deliberately used `[skip ci]`
because pre-existing live-scan and hourly historical workflows were active; no
generated corpus files were written concurrently and no duplicate collector was
launched.

Immediate growth target: after the active writer lanes clear, run the focused
Bagshaws saved-narrative collector, bank the ten rows, rebuild the database and
verify publication from the resulting checkpoint. Different researched
follow-on: the retained Bagshaws Uttoxeter page dated 10 May 2023 names seven
sold properties with seven achieved prices and explicitly reports a 100%
clearance. Bank those seven rows next, excluding the £/acre comparisons and the
previously saved navigation card from net growth. Keep both events and national
coverage incomplete unless their original lot inventories reconcile.

## Latest persisted collection handoff — 5 November 2026 (Bagshaws September 2025)

The retained Bagshaws Bakewell page dated 22 September 2025 has now been
reparsed and banked from its immutable first-party HTML snapshot. Ten named
appearances were added: six sold properties with achieved prices, Hollyseat
Cottage sold prior with a null price, and three available properties whose
individual outcome remains unknown because the page only says they "did not
sell or were postponed". That wording is preserved verbatim; no unsupported
unsold or postponed status was assigned. The £1.85m aggregate was excluded.

Net gain: 10 appearances, 10 address records and 10 exact-dated records inside
the preceding 20-year window. Two are land and eight unknown; none are
commercial or mixed-use. The gain contains six achieved prices, no guide prices
and no rents, with no new partial, undated, future-dated or duplicate result
identities. No source-year was opened because Bagshaws 2025 was already
represented. Bagshaws now has 298 appearances. The rebuilt corpus totals are
310,661 appearances, 299,709 address records, 302,400 in-window appearances,
104,815 in-window guides and 112,064 in-window achieved prices. An intervening
bounded run banked 492 records from other sources before this focused run; those
unrelated rows are deliberately excluded from the Bagshaws gain.

Ambiguity-preserving parser release:
`ef5696415bea0430ea0d5ee0cf07043884542337`; focused price-evidence trigger
`f68ec8dd31b6f426b3b6923f8a1414d94528eb1f`; successful collection and rebuild
run `42109099934`; banked evidence
`6b94a4582be87708ce227277ee70ac25fe4d82e3`; verified GitHub Pages and
auctiongeek.co.uk publication run `42109926388`.

Next concrete growth target: run the prepared retained Bagshaws Uttoxeter page
dated 10 May 2023 (`uttoxeter-land-and-property-auction-may-2023`). Its seven
named sold appearances have seven individual achieved prices, exact dates and
original saved-page evidence. Exclude the three published per-acre comparisons
and the previously saved navigation card from net growth. The importer and 126
tests are persisted in `edd3911412f52b1999a0bfad209dfbc6e209b3d9`; a local
saved-snapshot dry run yields seven new address rows, all sector-unknown, with
no guides, rents, partial, undated, future-dated or duplicate rows. At this
handoff, the separate live-snapshot revalidation from the September trigger
remains active in checkout; preserve its eventual checkpoint and do not overlap
or rerun it. National completeness remains false.

## Latest persisted collection handoff — 5 November 2026 (Bagshaws Uttoxeter May 2023)

The retained Bagshaws Uttoxeter page dated 10 May 2023 has now been reparsed
and banked from its immutable first-party HTML snapshot. Seven individually
named properties were added, all sold with achieved prices. The three
published per-acre comparisons were excluded, and the previously banked
navigation-derived page card was preserved but excluded from this run's
growth. No unsupported guide price or rent was inferred.

Net gain: 7 appearances, 7 address records and 7 exact-dated records inside
the preceding 20-year window. All seven have sector unknown; none are
commercial or mixed-use. The gain contains 7 achieved prices, no guide prices
and no rents, with no new partial, undated, future-dated or duplicate result
identities. No source-year was opened because Bagshaws 2023 was already
represented. Bagshaws now has 305 appearances. The rebuilt corpus totals are
310,668 appearances, 299,716 address records, 302,407 in-window appearances,
104,815 in-window guides and 112,071 in-window achieved prices.

Prepared importer release: `edd3911412f52b1999a0bfad209dfbc6e209b3d9`;
focused exact-price trigger: `024bd92a46495875a3a50408dd26aebbb142285f`;
successful collection and rebuild run `42111797463`; banked evidence
`54dc2d3bbedf1aba8293fcb3ce50e04cf246d784`; verified GitHub Pages and
auctiongeek.co.uk publication run `42112420882`. Separate live-snapshot
revalidation run `42111797551` was cancelled while still in checkout with
production skipped; it wrote and published nothing, and was preserved without
retry.

Next concrete growth target: reparse the retained Bagshaws Uttoxeter page dated
23 September 2020
(`uttoxeter-property-auction-for-wednesday-23rd-september-2020`). It names
seven individual interests: Top House Farm at Prestwood, two distinct Leigh
Road land parcels, the Ellastone village land and the Hollington land each sold
with an achieved price; Heathy Grove Farm sold prior with a null price; and the
Fradley building plot withdrawn with a null price. Exclude all five published
per-acre comparisons and the previously saved navigation card from net growth.
Keep the two Leigh Road parcels separate legal interests, preserve the saved
snapshot and leave the event and national completeness false until its original
lot inventory reconciles.


## Latest persisted collection handoff — 5 November 2026 (Bagshaws September 2020 and March 2026)

Two retained Bagshaws first-party narrative inventories have now been reparsed,
banked and rebuilt. The Uttoxeter page dated 23 September 2020 contributes seven
net-new named interests: five sold with achieved prices, Heathy Grove Farm sold
prior and the Fradley building plot withdrawn. The Bakewell page dated 23 March
2026 contributes nine net-new named interests: five sold with achieved prices
and four unsold with sale prices left null. The two Leigh Road parcels remain
separate legal interests. All five September 2020 per-acre comparisons and the
March 2026 aggregate of just under £1 million were excluded. Previously banked
navigation-derived page cards were preserved and excluded from net growth.

Combined net gain: 16 appearances, 16 address records and 16 exact-dated records
inside the preceding 20-year window. Five are land, two residential and nine
unknown; none are commercial or mixed-use. The gain contains 10 achieved prices,
no guide prices and no rents. Outcomes comprise 10 sold, four unsold, one sold
prior and one withdrawn. No partial, undated, future-dated or duplicate result
identity was added. No source-year was opened because Bagshaws 2020 and 2026
were already represented. The rebuilt corpus totals are 310,684 appearances,
299,732 address records, 302,423 in-window appearances, 104,815 in-window guides
and 112,081 in-window achieved prices. Bagshaws now has 321 appearances.
National completeness remains false.

September collector release:
`a2e1829f30d0fbdeb692493155988023627e0533`; successful collection and rebuild
run `42118834218`; banked evidence
`53370dbb3fcb1a4fd5a33322f8ab2ef236857ebf`; verified GitHub Pages and
auctiongeek.co.uk publication run `42119978024`. March collector release:
`30b88156236d56f6a03397ce84c3b951c8f22b90`; successful collection and rebuild
run `42121541327`; banked evidence
`8a0e8b1fe5f1effdcabcbefee29c743a7f1f2dd5`; verified GitHub Pages and
auctiongeek.co.uk publication run `42122284226`. Separate live-snapshot
revalidation runs `42118834256` and `42121541407` were preserved with
production skipped. The first failed safely because Auction House Cumbria and
Auction House National Online each remained at 50% rich-particular coverage
against 60%; neither revalidation contributed to the historical gain.

Next concrete growth target: bank the 14 named interests already verified in
three retained Bagshaws narrative snapshots. The 18 November 2019 Bakewell page
contains six named outcomes: three priced sales, Church Street at Brassington
sold prior, and two unsold properties. The 9 August 2023 Uttoxeter page contains
three individually priced land sales; its three unnamed reserve failures remain
excluded. The 24 March 2025 Bakewell page contains five individually priced land
sales, keeping Church Road and Blackwell Lots A and B and Foxholes Lane Lot B as
separate legal interests. Preserve exact dates, outcomes and achieved prices,
exclude every aggregate or unnamed result, reconcile exact-event overlaps and
leave all three events incomplete unless their original lot inventories
reconcile. A different retained November 2019 Uttoxeter narrative also contains
guide-price evidence; do not collect it until the narrative importer can carry
that guide distinctly rather than dropping it.

## 2026-11-05 Bagshaws saved-narrative expansion: 30 banked appearances

Two focused releases converted named property-level results already present in immutable first-party Bagshaws snapshots instead of refreshing exhausted archive routes.

- Release `452053c3170eb385858c4e6710f52a0dfbd4b5e5` banked 14 exact-dated appearances from Bakewell 18 November 2019, Uttoxeter 9 August 2023 and Bakewell 24 March 2025.
- Release `f7e11dbb438694e1c0d190c1780499cd6ec3d613` added a reusable distinct narrative guide-price field and banked 16 exact-dated appearances from Uttoxeter 20 November 2019, 21 July 2021, 25 May 2022 and 20 July 2022.
- Combined net gain: 30 appearances, 30 address records and 30 preceding-20-year records; 1 commercial, 0 mixed-use, 11 land and 18 unknown-sector records.
- Actual new price evidence: 1 guide and 23 achieved prices. Rent evidence: 0. Newly covered source-years: 0.
- Outcomes: 23 sold, 3 sold-prior, 3 unsold and 1 withdrawn. Unknown prices remain null.
- Partial, undated, future-dated and duplicate gains: 0 / 0 / 0 / 0.
- Ambiguous unnamed multi-lot references at Hixon and Gravelly Lane were excluded; per-acre comparisons were not treated as sale prices. Firs Farm and all other separable legal interests retain distinct identities.
- Canonical collection runs: [42126987471](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42126987471) and [42129101497](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42129101497). Bank commits: `f2629b7109528a8e5381df1b9ed8d40367f9d2d7` and `060da526e265269573032ecdb6af0433bc0a28e8`.
- Verified publication runs: [42127598918](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42127598918) and [42130640821](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42130640821), including Pages and auctiongeek.co.uk.
- Separate revalidation run [42129101559](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42129101559) failed safely without publishing: Auction House Cumbria rich particulars remain 50.0% and Auction House National Online 57.1% against the 60% gate. Production was skipped and the failure was not retried.
- A temporary fallback branch also triggered the all-branches workflow; repository concurrency kept the intended main run pending, so generated-data writes were not concurrent. Its isolated branch checkpoint is not counted separately.
- Rebuilt totals: 310,714 appearances, 299,762 address records, 302,453 preceding-20-year appearances, 104,816 guide prices, 112,104 achieved prices and 351 Bagshaws appearances. Partial 10,952; undated 5,016; future-dated 150.
- National completeness remains false.

Next concrete growth target: the retained Bagshaws Bakewell 25 September 2023 narrative. It identifies eight separable property appearances: two Quarnford interests sharing only an aggregate £460,000 result (individual sale prices must remain null), five individually achieved prices, and the Moor Edge, Birch Vale development site sold immediately after auction. The three unnamed sold-prior lots and unnamed unsold properties must remain excluded.

## 2026-11-06 Bagshaws Bakewell 25 September 2023 saved narrative

- Focused release `0ea157b89c11111734f5e43e1282fdbe415c9824` parsed eight separable, exact-dated property appearances from the retained first-party page.
- Canonical collection run [42133502833](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42133502833) banked 8 appearances, 8 address records and 8 newly captured preceding-20-year records. Bank commit: `7e1c0fd3c85cecb7885e9af3553beb67d5c88fc9`.
- Net sector gain: 0 commercial, 0 mixed-use, 2 land, 1 residential and 5 unknown.
- Actual new price evidence: 0 guides, 5 achieved prices and 0 rents. Newly covered source-years: 0.
- Outcomes: seven sold and one sold-after. The two Quarnford interests share only an aggregate £460,000 result, so each individual sale price remains null while the collective figure is preserved in result text.
- Three unnamed sold-prior lots and unnamed unsold properties were excluded. Partial, undated, future-dated and duplicate gains are 0 / 0 / 0 / 0; the event remains an incomplete inventory.
- Validation passed 171 focused tests.
- Publication run [42134181583](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42134181583) successfully deployed both Pages and auctiongeek.co.uk.
- Rebuilt totals: 310,722 appearances, 299,770 address records, 302,466 preceding-20-year appearances, 104,817 in-window guides, 112,109 in-window achieved prices and 359 Bagshaws appearances. Partial 10,952; undated 5,016; future-dated 145.
- The calendar rollover to 6 November moved five pre-existing records out of the future-dated bucket and into the 20-year reporting window, including one pre-existing guide. Those changes are not attributed to this collection gain.
- Separate revalidation run [42133502795](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42133502795) failed safely without publishing: Auction House Cumbria remains at 50.0% and Auction House National Online at 57.1% rich-particular coverage against the 60% gate. Production was skipped and the known route was not retried.
- National completeness remains false.

Next concrete growth target: the retained Bagshaws Bakewell 22 November 2021 narrative. It identifies nine separable appearances: three sold land interests whose published amounts are per-acre comparisons rather than individual achieved prices, two named sold-prior properties, 1 Pomeroy Cottages sold after auction, Brierlow Bar Farm postponed, and Ellergreaves Farm plus Westhaven/The Beeches unsold. Unknown individual prices must remain null.

### 2026-11-06 focused Bagshaws Bakewell November 2021 narrative bank

- Growth opportunity executed: uncaptured individual outcomes in the already retained Bagshaws narrative for **Bakewell, 22 November 2021**. Release commit `a96992da69fb042f0afef15315bcfbc0c278efc8` added an explicit, tested nine-row narrative inventory rather than refreshing the exhausted archive.
- Collection run [42141108883](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42141108883) completed successfully and banked generated evidence in commit `c9f18bcfcf5b248debd7161e47af3734ed3a9c26`.
- Net newly banked appearances: **9**; newly address-bearing records: **9**; exact-dated records inside the current 20-year window: **9**; partial: **0**; undated: **0**; future-dated: **0**; duplicates claimed as growth: **0**.
- Newly banked sectors: **2 land**, **7 unknown**; commercial: **0**; mixed-use: **0**.
- Newly banked outcomes: **3 sold**, **2 sold prior**, **1 sold after**, **1 postponed**, **2 unsold**. The two published per-acre comparisons remain in outcome evidence text and were not promoted to individual achieved prices.
- New guide-price evidence: **0**; new individual achieved-price evidence: **0**; new rent evidence: **0**; newly covered source-years: **0**. The retained narrative page has no original catalogue denominator, so no catalogue-completeness claim was added.
- Rebuilt totals: **310,731** appearances; **299,779** address-bearing records; **302,475** appearances in the current 20-year window; **104,817** with guide prices; **112,109** with achieved prices; Bagshaws **368**. Remaining corpus classifications: **10,952 partial**, **5,016 undated**, **145 future-dated**.
- Verification: **173 tests passed** locally before release; the collector reported no failures. Public-platform run [42141690036](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42141690036) completed successfully for both GitHub Pages and `auctiongeek.co.uk`.
- The release-triggered revalidation run [42141108867](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42141108867) was cancelled after the newer bank publication superseded it; it was not retried because the successful bank publication already preserved the checkpoint.
- Next concrete growth target: parse the five named, uncaptured interests in the retained Bagshaws **Uttoxeter, 30 April 2025** narrative: Lot 6, 4.27 acres off Woodhouses Road, Burntwood (sold for **£162,000**); Land at Blunts Hollow (Lot B), 36a Heath Road and the Building Plot at Pipehill (unsold/private treaty); and Land off Commonside, Gentleshaw, Rugeley (re-entered/postponed). Exclude the unnamed sold-prior reference, and retain the published £37,939-per-acre comparison as evidence text rather than a sale price.
- National completeness remains **false** pending source-by-source lot-inventory and auctioneer/branch/trading-name reconciliation.

### 2026-11-06 focused Bagshaws Uttoxeter April 2025 narrative bank

- Growth opportunity executed: five named, uncaptured interests in the retained first-party Bagshaws narrative for **Uttoxeter, 30 April 2025**. Release commit `f5a8cb0be7d758437bf87eef4e6e59c2c0fb5aac` added an explicit tested inventory rather than refreshing the archive.
- Collection run [42147559424](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42147559424) completed successfully and banked generated evidence in commit `ea25df3de999d08c8353a9f0448e30233074d225`.
- Net newly banked appearances: **5**; newly address-bearing records: **5**; exact-dated records inside the current 20-year window: **5**; partial: **0**; undated: **0**; future-dated: **0**; duplicates claimed as growth: **0**.
- Newly banked sectors: **3 land**, **2 unknown**; commercial: **0**; mixed-use: **0**.
- Newly banked outcomes: **1 sold**, **3 unsold/private-treaty**, **1 postponed/re-entered**. The unnamed sold-prior lot was excluded. Lot 6's **£162,000** is retained as the individual achieved price; the published **£37,939 per acre** comparison remains only in result evidence.
- New guide-price evidence: **0**; new individual achieved-price evidence: **1**; new rent evidence: **0**; newly covered source-years: **0**. The retained narrative has no original catalogue denominator, so no catalogue-completeness claim was added.
- Rebuilt totals: **310,736** appearances; **299,784** address-bearing records; **302,480** appearances in the current 20-year window; **104,817** with guide prices; **112,110** with achieved prices; Bagshaws **373**. Remaining corpus classifications: **10,952 partial**, **5,016 undated**, **145 future-dated**.
- Verification: **175 tests passed** before release; the collector reported no failures. Public-platform run [42148132178](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42148132178) completed successfully for both GitHub Pages and `auctiongeek.co.uk`.
- Separate revalidation run [42147559449](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42147559449) revalidated 904 published rows but added **0** fresh reclassified lots and failed safely without production publication on the known 60% rich-particular gate: Auction House Cumbria **50.0%** and Auction House National Online **57.1%**. The blocked route was preserved and not retried.
- Next concrete growth target: run the already configured isolated shared-platform collector for **Auction House Online event 74284, dated 14 October 2025**, whose source contract expects **44 visible first-party cards** at `https://online.auctionhouse.co.uk/past-auctions/74284?lotResultType=All`. Its auction directory is currently absent, so this is a substantial uncollected catalogue rather than a refresh. Preserve individual dates, branch attribution, guides, achieved prices, rents, outcomes, URLs and immutable index/detail snapshots; exclude only exact overlaps.
- National completeness remains **false** pending source-by-source lot-inventory and auctioneer/branch/trading-name reconciliation.

## 2026-11-06 Auction House Online event reconciliation and November 2023 growth

The run first executed the persisted Auction House Online event `74284`, dated
14 October 2025. The strict first-party inventory reconciled all **44 of 44**
visible cards and retained the event index plus all 44 detail snapshots (index
SHA-256 `72e0205dd64abac17743f28a3bb515040671c38b589c15fba9b43ef6658eeff1`).
It added **0 net appearances**: 13 source identities were already present and
the other 31 cards were exact date/address overlaps. Therefore no appearances,
addresses, in-window addresses, commercial or mixed-use rows, guides, achieved
prices, rents, partial, undated, future-dated, duplicate identities or new
source-years are claimed as growth from that event. The complete surviving
event inventory and overlap evidence remain banked rather than discarded.
Collector hardening release `32c5b3cfda7be09bf2b756dbaa74aec35ab7edb4`,
collection run [42154578099](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42154578099),
bank commit `48d9842aa0660e5af81d59ba7542a1a76da32da3` and publication run
[42155157418](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42155157418)
are preserved. Pages and `auctiongeek.co.uk` both succeeded.

The run then moved to a materially different, previously unconfigured catalogue:
Auction House Online event `53349`, principally dated 21 November 2023. The
first-party all-results page exposed **31 of 31** property cards. Release
`f369b78d651132b52cf1802a66735569747c0c6b` added its strict source contract,
focused regression assertion and isolated workflow trigger; **183 focused tests
passed** before release. Collection run
[42156317275](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42156317275)
reconciled all 31 stable identities and all 31 detail pages with immutable
snapshots (index SHA-256
`e3cdce2aec3d01c2ba090d583d6691c8614efc2efd6ad060683d86c562f11bd4`).

Net banked gain after exact-overlap exclusion: **14 appearances**, **14 address
records** and **14 exact-dated records inside the preceding 20-year window**.
Seventeen exact date/address overlaps were excluded; duplicate source identities
were **0**, and no captured record was discarded. The additions comprise **1
commercial**, **0 mixed-use**, one land, five residential and seven
unknown-sector appearances. Actual new evidence is **14 guide prices**, **2
achieved sale prices** and **1 rent value**. Outcomes remain distinct: two sold,
nine unsold, one postponed and two withdrawn. Partial, undated and future-dated
gains are all **0**. Individual published dates from 17 to 21 November 2023 are
retained.

One isolated **Auction House Online / 2023 source-year** is newly reconciled;
this is not a new legal operator. Auction House North West, South West, East
Anglia, London, Scotland and Lincolnshire remain branch attribution under
AUCTION HOUSE UK LIMITED (company 06025583), not additional auctioneers. Bank
commit: `1d1d0d5577bcc1b82aee50b5cdb2818793617a37`. Publication run
[42156861250](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42156861250)
completed successfully for both Pages and `auctiongeek.co.uk`.

Rebuilt corpus totals are **310,750 appearances**, **299,798 address records**,
**302,494 in-window appearances**, **104,831 in-window guides** and **112,112
in-window achieved prices**. Remaining classifications are **10,952 partial**,
**5,016 undated** and **145 future-dated**; complete surviving catalogue states
are **4,510**, incomplete/unreconciled states **556**, and fetch/parse failures
**31**. National completeness remains **false**.

The release-triggered revalidation runs
[42154578208](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42154578208)
and [42156317292](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42156317292)
were preserved as cancelled during checkout with production skipped. Neither
revalidated, wrote historical evidence or published, and neither was retried.

Next concrete growth target: Auction House Online event
[`53159`](https://online.auctionhouse.co.uk/past-auctions/53159?lotResultType=All),
principally dated 14 November 2023. The surviving first-party page reports
**41 of 41 property cards** with individual dates from 6 to 14 November 2023,
including commercial investments, land, guides, achieved prices and rent
evidence. Add one strict 41-card source contract and isolated trigger after
writer clearance, preserve each individual date/outcome/price/rent and immutable
index/detail snapshot, and exclude exact overlaps before claiming growth.



## 2026-11-06 Auction House Online 14 November 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `53159`, principally dated 14 November 2023. Release `c79a76da9051c1db6b2d2609c22d930bc408dade` added a strict 41-card first-party source contract, regression assertion and isolated workflow step. The focused collector/workflow suite passed **155 tests** before release.
- Collection run [42160308539](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42160308539) reconciled **41 of 41** visible cards and all 41 detail pages without failures. The immutable index snapshot has SHA-256 `4f4d81019af7e80e99ae60151d3d73f04989e9dd939084da713d42d2fd1b2892`; bank commit: `a17eb78788c66b593f8ca77e7dc47198992540bb`.
- Net newly banked growth after exact-overlap exclusion: **21 appearances**, **21 address records** and **21 exact-dated address records inside the current 20-year window**. Twenty exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 3 land, 6 residential and 11 unknown. Branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **21 guide prices**, **1 achieved sale price** and **1 rent value**. Outcomes remain separate: one sold, one sold after, one sold prior, 14 unsold, three withdrawn and one postponed. Partial, undated and future-dated gains are all **0**; individual dates from 6 to 14 November 2023 are retained.
- The collector's event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented by event 53349. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event, avoiding source-year inflation.
- Rebuilt totals: **310,771 appearances**, **299,819 address records**, **302,515 in-window appearances**, **104,852 in-window guides** and **112,113 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. National completeness remains **false**.
- Publication run [42160689232](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42160689232) completed successfully for both Pages and `auctiongeek.co.uk`. No collector or generated-data writer remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`53377`](https://online.auctionhouse.co.uk/past-auctions/53377?lotResultType=All), principally dated 28 November 2023. Its surviving first-party page reports **27 of 27 property cards**, with individual dates, guides and numerous achieved prices, and the event is absent from the collector configuration. Preserve all detail-derived branch attribution, dates, outcomes, guides, achieved prices, rents, original URLs and immutable snapshots; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 28 November 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `53377`, principally dated 28 November 2023. Release `e884ea1cb061f89defc5d14548d14068184415b0` added its strict 27-card first-party source contract, regression assertion and isolated workflow step. The focused collector/workflow suite passed **155 tests** before release.
- Collection run [42166055674](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42166055674) reconciled **27 of 27** visible cards and all 27 detail pages without failures. The immutable index snapshot has SHA-256 `228fa5963adcc9203a721d2e2ed9448ff6d8dfef3ccb742f329ebddec8fd4d0e`; bank commit: `9310d3894f28b797f893b70a13dfa1c2598f2154`.
- Net newly banked growth after exact-overlap exclusion: **7 appearances**, **7 address records** and **7 exact-dated address records inside the current 20-year window**. Twenty exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 4 residential and 2 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **7 guide prices**, **0 achieved sale prices** and **0 rent values**. Outcomes remain separate: one sold prior, four unsold and two postponed. Partial, undated and future-dated gains are all **0**; individual dates from 23 to 28 November 2023 are retained.
- The collector's event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented by events 53349 and 53159. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event, avoiding source-year inflation.
- Rebuilt totals: **310,778 appearances**, **299,826 address records**, **302,522 in-window appearances**, **104,859 in-window guides** and **112,113 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,518**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42166597551](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42166597551) completed successfully for both Pages and `auctiongeek.co.uk`. No collector or generated-data writer remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`53027`](https://online.auctionhouse.co.uk/past-auctions/53027?lotResultType=All), principally dated 7 November 2023. The surviving first-party results index inventories **30 lots**, including guides, achieved prices, rent and mixed-use evidence, and the event is absent from the collector configuration. Preserve each individual date, detail-derived branch attribution, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 7 November 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `53027`, principally dated 7 November 2023. Release `750a2c919c20719c6db61323ba6a32d0ebd748c2` added its strict 30-card first-party source contract, regression assertion and isolated workflow step. The focused collector/workflow suite passed **155 tests** before release.
- Collection run [42171704332](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42171704332) reconciled **30 of 30** visible cards and all 30 detail pages without failures. The immutable index snapshot has SHA-256 `e5f6202dbe104124e3ab552722689145351504cbda597efc116c1f59c6487a35`; bank commit: `0123802aeb7d1f59e360a5d03ae0b51c59162557`.
- Net newly banked growth after exact-overlap exclusion: **12 appearances**, **12 address records** and **12 exact-dated address records inside the current 20-year window**. Eighteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 3 land, 4 residential and 5 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **12 guide prices**, **2 achieved sale prices** and **1 rent value**. Outcomes remain separate: two sold, two sold prior, one sold after and seven unsold. Partial, undated and future-dated gains are all **0**; individual dates from 6 November to 5 December 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,790 appearances**, **299,838 address records**, **302,534 in-window appearances**, **104,871 in-window guides** and **112,115 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,521**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Initial publication run [42172256482](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42172256482) preserved the tested 193 MB Pages artifact but was cancelled when `actions/deploy-pages@v4` exceeded the former 15-minute job ceiling; its custom-domain job was skipped. Publication repair `e0ac59dc331f3947248acc8c1d8ee269fc1f38ff` raised the bounded job timeout to 25 minutes. Retry run [42173963927](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42173963927) then completed successfully for both Pages and `auctiongeek.co.uk`. No collector or generated-data writer remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`52578`](https://online.auctionhouse.co.uk/past-auctions/52578?lotResultType=All), principally dated 31 October 2023. The surviving first-party all-results page exposes **33 of 33 property cards**, includes guides and achieved-price evidence, and the event is absent from the collector configuration. Preserve every individual date, detail-derived branch attribution, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 31 October 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `52578`, principally dated 31 October 2023. Release `42f9773ae9db6d2db14094b3d50327b376a64938` added its strict 33-card first-party source contract, regression assertion and isolated workflow step. The focused collector/workflow suite passed **155 tests** before release.
- Collection run [42178907917](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42178907917) reconciled **33 of 33** visible cards and all 33 detail pages without failures. The immutable index snapshot has SHA-256 `67b3f5f19a80c9196ebff5d805ff8438651f96ded851a9c29bc242f79f329c8f`; bank commit: `4e88168323214eb02912ea85ce058ac40656ecd9`.
- Net newly banked growth after exact-overlap exclusion: **20 appearances**, **20 address records** and **20 exact-dated address records inside the current 20-year window**. Thirteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **1 mixed-use**, 9 residential and 9 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **20 guide prices**, **1 achieved sale price** and **0 rent values**. Outcomes remain separate: one sold, six sold prior, nine unsold, three postponed and one withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 5 to 31 October 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,810 appearances**, **299,858 address records**, **302,554 in-window appearances**, **104,891 in-window guides** and **112,116 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,527**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42179420081](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42179420081) completed successfully for both Pages and `auctiongeek.co.uk`.
- The protected scheduled scan run [42176273843](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42176273843) preserved its candidate checkpoint and published nothing after validation rejected live-source rich-particular coverage below 60% for Auction House Cumbria (50.0%) and Auction House National Online (57.1%). No records were discarded; this material blocker is recorded without interrupting the independent historical bank.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`52515`](https://online.auctionhouse.co.uk/past-auctions/52515?lotResultType=All), principally dated 24 October 2023. The surviving first-party results index inventories **21 lots**, and the event page retains individual dates, guides, sold prices and rent evidence while remaining absent from the collector configuration. Preserve every individual date, detail-derived branch attribution, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 24 October 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `52515`, principally dated 24 October 2023. Release `90755667f18b6be662a475e650137d8bec34d761` added its strict 21-card first-party source contract, regression assertion and isolated workflow step. The focused collector/workflow suite passed **155 tests** before release.
- Collection run [42185115618](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42185115618) reconciled **21 of 21** visible cards and all 21 detail pages without failures. The immutable index snapshot has SHA-256 `7c627014f3b204c7cdad9ca6e3c6ebced4d7aa784b040ca89a07eb4ebff044b4`; bank commit: `cb30559e6afeb6c26c33be5c53b7f67dcfd4d546`.
- Net newly banked growth after exact-overlap exclusion: **6 appearances**, **6 address records** and **6 exact-dated address records inside the current 20-year window**. Fifteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 1 residential, 1 land and 4 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **6 guide prices**, **1 achieved sale price** and **0 rent values**. Outcomes remain separate: one sold, four unsold and one withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 23 to 24 October 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,816 appearances**, **299,864 address records**, **302,560 in-window appearances**, **104,897 in-window guides** and **112,117 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,529**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42185609019](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42185609019) completed successfully for both Pages and `auctiongeek.co.uk`. No collector or generated-data writer remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`52311`](https://online.auctionhouse.co.uk/past-auctions/52311?lotResultType=All), principally dated 17 October 2023. The surviving first-party results index inventories **36 lots** and retains individual result evidence, while the event is absent from the collector configuration. Preserve each individual date, detail-derived branch attribution, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 17 October 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `52311`, principally dated 17 October 2023. Release `b60a6c071e171e6eefd6c670812a589a28048b8e` added its strict 36-card first-party source contract, regression assertion and isolated workflow step. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42192319777](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42192319777) reconciled **36 of 36** visible cards and all 36 detail pages without failures. The immutable index snapshot has SHA-256 `c98a40c6f157dc21647c333f08518df90a0bb0b93d670b6638a97a71bac723f0`; bank commit: `58fe7ddcfb77f4b65fcf412f60bf050daa037dbd`.
- Net newly banked growth after exact-overlap exclusion: **24 appearances**, **24 address records** and **24 exact-dated address records inside the current 20-year window**. Twelve exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 6 land, 7 residential and 11 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **24 guide prices**, **4 achieved sale prices** and **1 rent value**. Outcomes remain separate: four sold, 15 unsold, four postponed and one withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 9 to 17 October 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,840 appearances**, **299,888 address records**, **302,584 in-window appearances**, **104,921 in-window guides** and **112,125 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,532**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42193232796](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42193232796) successfully tested and deployed GitHub Pages. The custom-domain build and Wrangler dry-run also passed, but the Cloudflare Worker deployment received provider-side HTTP 503 responses on both the initial upload-session request and the single failed-job retry (`upstream connect error`, then `no healthy upstream`). Evidence artifacts `13491521381` and `13491009164` were preserved. No further retry was launched against the same blocked route.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`52101`](https://online.auctionhouse.co.uk/past-auctions/52101?lotResultType=All), principally dated 10 October 2023. The surviving first-party results index exposes **24 of 24** property cards with individual dates, guides, achieved prices, rent and land evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 10 October 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `52101`, dated 10 October 2023. Release `d057553947b124df4d4ab7e656b94d87de0ec6af` added its strict 24-card first-party source contract, regression assertion and isolated workflow step. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42199076987](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42199076987) reconciled **24 of 24** visible cards and all 24 detail pages without failures. The immutable index snapshot has SHA-256 `689bef6237c33757e1fb49c67e0ecf60d4a9ce7daffbcac4b78fcc8e22f3fefc`; bank commit: `b232f727393d56c7af3444402e0cd435fb4a8e27`.
- Net newly banked growth after exact-overlap exclusion: **9 appearances**, **9 address records** and **9 exact-dated address records inside the current 20-year window**. Fifteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 6 land and 3 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **9 guide prices**, **4 achieved sale prices** and **0 rent values**. Outcomes remain separate: four sold and five unsold. Partial, undated and future-dated gains are all **0**; every newly banked record retains the exact 10 October 2023 auction date.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,849 appearances**, **299,897 address records**, **302,593 in-window appearances**, **104,930 in-window guides** and **112,129 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,533**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42199794562](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42199794562) completed successfully for both GitHub Pages and `auctiongeek.co.uk`. The fresh successful custom-domain deployment supersedes the preserved provider-side Cloudflare 503 checkpoint from the preceding publication; the failed evidence artifacts remain intact.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51829`](https://online.auctionhouse.co.uk/past-auctions/51829?lotResultType=All), principally dated 3 October 2023. The surviving first-party results page exposes **45 of 45** property cards with individual outcomes and achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 3 October 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `51829`, principally dated 3 October 2023. Release `887b15b111bd04a75c4e25c945246865d984b453` added its strict 45-card first-party source contract, regression assertion and isolated workflow step. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42206787327](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42206787327) reconciled **45 of 45** visible cards and all 45 detail pages without failures. The immutable index snapshot has SHA-256 `b75fa3225c9034dce68a9c480e00ca722b7bc4410df7d7f87998ea03fb488086`; bank commit: `9c07eff226cd5d8aef54cd6d1d03ae1390b6b4a1`.
- Net newly banked growth after exact-overlap exclusion: **28 appearances**, **28 address records** and **28 exact-dated address records inside the current 20-year window**. Seventeen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 17 residential and 10 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **28 guide prices**, **0 achieved sale prices** and **0 rent values**. Outcomes remain separate: two sold prior, one sold after, five unsold, five postponed and 15 withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 29 September to 3 October 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,877 appearances**, **299,925 address records**, **302,621 in-window appearances**, **104,958 in-window guides** and **112,129 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,536**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42207426277](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42207426277) completed successfully for both GitHub Pages and `auctiongeek.co.uk`. No collector, database writer or publisher remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51822`](https://online.auctionhouse.co.uk/past-auctions/51822?lotResultType=All), dated 26 September 2023. The surviving first-party results page exposes **30 of 30** property cards with individual guides, rents, outcomes and achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 26 September 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `51822`, dated 26 September 2023. Release `4f265d9c13a963832d163187a6b9c6606c296d87` added its strict 30-card first-party source contract, regression assertion and isolated workflow step. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42214955987](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42214955987) reconciled **30 of 30** visible cards and all 30 detail pages without failures. The immutable index snapshot has SHA-256 `4d19aa1ddda091d930cd0acedbf856ff8f1b6f36c892a5104f83e7bd79484a72`; bank commit: `a27aabd4b4b4a5c95e3a63abaf8938ad87b45e8d`.
- Net newly banked growth after exact-overlap exclusion: **9 appearances**, **9 address records** and **9 exact-dated address records inside the current 20-year window**. Twenty-one exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 2 residential and 6 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **9 guide prices**, **0 achieved sale prices** and **0 rent values**. Outcomes remain separate: six unsold, two withdrawn and one postponed. Partial, undated and future-dated gains are all **0**; individual dates from 19 to 26 September 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,886 appearances**, **299,934 address records**, **302,630 in-window appearances**, **104,967 in-window guides** and **112,129 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,539**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42215697846](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42215697846) completed successfully for both GitHub Pages and `auctiongeek.co.uk`. No collector, database writer or publisher remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51559`](https://online.auctionhouse.co.uk/past-auctions/51559?lotResultType=All), principally dated 19 September 2023. The surviving first-party results page exposes **18 of 18** property cards, including office, land, tenanted property, guide, rent, outcome and achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 19 September 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `51559`, principally dated 19 September 2023. Release `bdf0f51e81b2044d11cb024ca147b08b98bd7efc` added its strict 18-card first-party source contract, regression assertion and isolated workflow step. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42222744794](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42222744794) reconciled **18 of 18** visible cards and all 18 detail pages without failures. The immutable index snapshot has SHA-256 `76e94634ca3a94bc19afe55fc2a34876c88b92794782353c2800567a09f7ee8e`; bank commit: `6493a8e71fce8f84f4cf7f5bdf56686eeedfd65c`.
- Net newly banked growth after exact-overlap exclusion: **14 appearances**, **14 address records** and **14 exact-dated address records inside the current 20-year window**. Four exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 2 land, 6 residential and 6 unknown. Detail-derived branch attribution remains under AUCTION HOUSE UK LIMITED (company 06025583) rather than creating new auctioneers.
- Actual new evidence: **14 guide prices**, **2 achieved sale prices** and **1 rent value**. Outcomes remain separate: two sold, one sold prior, one sold after, seven unsold and three postponed. Partial, undated and future-dated gains are all **0**; individual dates from 12 to 19 September 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. Therefore this handoff counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,900 appearances**, **299,948 address records**, **302,644 in-window appearances**, **104,981 in-window guides** and **112,131 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,016 undated** and **145 future-dated**. Complete surviving catalogue states are **4,542**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42224219262](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42224219262) completed successfully for both GitHub Pages and `auctiongeek.co.uk`. No collector, database writer or publisher remained active at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51451`](https://online.auctionhouse.co.uk/past-auctions/51451?lotResultType=All), principally dated 12 September 2023. The surviving first-party results page exposes **14 of 14** property cards with rent, guide, outcome and extensive achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.


## 2026-11-06 Auction House Online 12 September 2023 catalogue and saved-source bank

- Growth opportunity executed: previously unconfigured Auction House Online event `51451`, principally dated 12 September 2023. Source-contract commit `2b08518c9ce14188d565c20ab168d1b4fe2586e3`, regression commit `20d9340d21f103686c9e82f6c87ee42ec9e319d5` and isolated-workflow commit `6deed37a15d03692b7ad15690cde2645c4b698d3` added and exercised its strict 14-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42229869280](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42229869280) reconciled **14 of 14** visible cards and all 14 detail pages without failures. The immutable index snapshot has SHA-256 `e44559a20b1e2493240e96e5af1e8274df767aae455dddf2adc4f289d1598aba`; bank commit: `1f411ea1af89303cf12d67cee017936ad128ced1`.
- Net event growth after exact-overlap exclusion: **7 appearances**, **7 address records** and **7 exact-dated address records inside the current 20-year window**. Seven exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net event sectors: **0 commercial**, **0 mixed-use**, 3 residential and 4 unknown. Detail-derived branches remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): West Yorkshire 1, Scotland 4, Online 1 and Lincolnshire 1; they are not counted as new auctioneers.
- Actual new event evidence: **7 guide prices**, **1 achieved sale price** and **0 rent values**. Outcomes remain separate: four unsold, one sold prior, one withdrawn and one sold. Event partial, undated and future-dated gains are all **0**; individual dates from 6 to 12 September 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Before the isolated event acquired the write lock, bounded continuation run [42229838685](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42229838685) banked **4 additional uncaptured address-bearing appearances** already present in saved source evidence: BTG Eddisons 1, Clarke & Simpson 1 and The Property Auction House 2. These remain separate from the event result: 3 residential and 1 unknown; 3 records carry a 2026 year and 1 is undated. No guide evidence was added. One achieved-price enrichment was added by the Auction Works refresh, while its one future-dated classification yielded **0 new appearances**. Precursor bank commit: `92b9a632367d35d43b846d661ba97bc69afd1b74`.
- Combined run growth relative to the preceding handoff is **11 appearances** and **11 address records**, but only the event's **7 exact-dated in-window address records** are claimed here as newly reconciled in-window growth. The saved-evidence bank's undated row and the separate future classification are not inflated into that measure.
- Rebuilt totals: **310,911 appearances**, **299,959 address records**, **302,650 in-window appearances**, **104,988 in-window guides** and **112,133 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **146 future-dated**. Complete surviving catalogue states are **4,545**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- The automatic target publication checkpoint was cancelled before jobs when a newer main revision replaced the pending run; no banked evidence was lost. Publication run [42235250895](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42235250895) then published main including bank `1f411ea1` successfully to both GitHub Pages and `auctiongeek.co.uk`. The preserved isolated retry [42235565218](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42235565218) also completed successfully on both channels. No collector, database writer or publisher remained active or queued at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51433`](https://online.auctionhouse.co.uk/past-auctions/51433?lotResultType=All), principally dated 5 September 2023. The surviving first-party results page exposes **26 of 26** property cards, including mixed-use and achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.


## 2026-11-06 Auction House Online 5 September 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `51433`, principally dated 5 September 2023. Source-contract commit `15e6bc0c74f4c0d5f1bbfef4f253bb70a7abad88`, regression commit `618f61db14b4a11af140df5e8f13d2f3656aa6e3` and isolated-workflow commit `26978bdf1718c4f1418108d01ecaa22c7aa89978` added and exercised its strict 26-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42248166564](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42248166564) reconciled **26 of 26** visible cards and all 26 detail pages without failures. The immutable index snapshot has SHA-256 `72b31655c82e630fc473be351ce00018dd928b7c6637671e6e74b0ed9328b09c`; bank commit: `935ab3a719b0967bb494a0d007f39011ecf0bde7`.
- Net event growth after exact-overlap exclusion: **8 appearances**, **8 address records** and **8 exact-dated address records inside the current 20-year window**. Eighteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 1 land, 2 residential and 5 unknown. Detail-derived branch labels remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): North West 1, Lincolnshire 1, Wales - Cardiff 1, Sussex & Hampshire 1 and Scotland 4; they are not counted as new auctioneers.
- Actual new event evidence: **8 guide prices**, **0 achieved sale prices** and **0 rent values**. Outcomes remain separate: six unsold and two postponed. Partial, undated and future-dated event gains are all **0**; individual dates from 4 to 5 September 2023 are retained.
- A separately scheduled, serial bounded collector then banked **2 additional address-bearing appearances** without overlapping the event: Auction House South West 1 and Bradley Hall 1. Both are future-dated 2026 records and therefore add **0 current 20-year appearances**; sectors are 1 residential and 1 land. Bradley Hall confirms **1 additional guide price**, while no additional achieved price or rent is claimed. Scheduled collection run: [42250285359](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42250285359); merged bank commit: `a1b1bb08260ed52761f6e5bb3641d31e508cda77`.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals after the serial merge: **310,921 appearances**, **299,969 address records**, **302,658 in-window appearances**, **104,996 in-window guides** and **112,133 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **151 future-dated**. Complete surviving catalogue states are **4,548**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Initial publication run [42248922592](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42248922592) published the event bank successfully. After the serial scheduled merge, publication run [42254334301](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42254334301) also completed successfully for both GitHub Pages and `auctiongeek.co.uk`. No collector, database writer or publisher remained active or queued at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`51014`](https://online.auctionhouse.co.uk/past-auctions/51014?lotResultType=All), principally dated 29 August 2023. The surviving first-party page exposes **13 of 13** property cards with guide, achieved-price, land and residential evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.



## 2026-11-06 Auction House Online 29 August 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `51014`, dated 29 August 2023. Source-contract commit `70ef5ce04842280b1724e554fedbc9073a42f243`, regression commit `8103dc20fb6499ad520b1422e69cbaa135541ef2` and isolated-workflow commit `831c1c81d9c697d38ad844b6d6e3b8ed355eac87` added and exercised its strict 13-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42258327255](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42258327255) reconciled **13 of 13** visible cards and all 13 detail pages without failures. The immutable index snapshot has SHA-256 `523faf01ed922a4b7d92c4e42d5a1597c22c5826e51c4a3cde54eb0841ddbc3c`; bank commit: `ca32fc70a4ca314294ff9e91cd762ee034963d17`.
- Net newly banked growth after exact-overlap exclusion: **7 appearances**, **7 address records** and **7 exact-dated address records inside the current 20-year window**. Six exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **0 commercial**, **0 mixed-use**, 1 land, 4 residential and 2 unknown. Detail-derived branch labels remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): North West 1, Birmingham 2, Scotland 1 and Sussex & Hampshire 3; they are not counted as new auctioneers.
- Actual new evidence: **7 guide prices**, **0 achieved sale prices** and **0 rent values**. All seven newly banked outcomes are unsold. Partial, undated and future-dated gains are all **0**; every new appearance retains the individual date 29 August 2023.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,928 appearances**, **299,976 address records**, **302,665 in-window appearances**, **105,003 in-window guides** and **112,133 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **151 future-dated**. Complete surviving catalogue states are **4,549**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42259156485](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42259156485) completed successfully for both GitHub Pages and `auctiongeek.co.uk`. No collector, database writer or publisher remained active or queued at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`50829`](https://online.auctionhouse.co.uk/past-auctions/50829?lotResultType=All), dated 22 August 2023. The surviving first-party results page exposes **41 of 41** property cards with individual guides, rents, tenanted-property evidence and achieved prices, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.


## 2026-11-06 Auction House Online 22 August 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `50829`, principally dated 22 August 2023. Source-contract commit `40f74526748833fbf5d7a639dca8877e561f65f5`, regression commit `2384b070d63cf88b61860d02049e13a37bddade7` and isolated-workflow commit `176c5cf22f24dd26bdbe178737efd740c621a644` added and exercised its strict 41-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42266616421](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42266616421) reconciled **41 of 41** visible cards and all 41 detail pages without failures. The immutable index snapshot has SHA-256 `ede177a749a5f28600244edbdcd6968af15f1edf8b4d63c37a6036861cc69326`; bank commit: `a75b6275d1b0c6d79fa440e00f9ede734d5c4e4e`.
- Net newly banked growth after exact-overlap exclusion: **19 appearances**, **19 address records** and **19 exact-dated address records inside the current 20-year window**. Twenty-two exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **1 mixed-use**, 1 land, 7 residential and 9 unknown. Detail-derived branch labels remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): Coventry and Warwickshire 1, East Anglia 1, South West 1, Hull & East Yorkshire 1, Notts & Derby 6, Cumbria 1, Cheshire, Staffordshire & Shropshire 2, Cheshire 3, Scotland 2 and North West 1; they are not counted as new auctioneers.
- Actual new evidence: **19 guide prices**, **0 achieved sale prices** and **1 rent value**. Outcomes remain separate: 15 unsold, two withdrawn, one sold prior and one postponed. Partial, undated and future-dated gains are all **0**; individual dates from 25 July to 22 August 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,947 appearances**, **299,995 address records**, **302,684 in-window appearances**, **105,022 in-window guides** and **112,133 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **151 future-dated**. Complete surviving catalogue states are **4,553**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42267422141](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42267422141) preserved the built Pages artifact and reconciliation evidence but did not publish this bank. Attempt 1 created the Pages deployment, which remained `deployment_queued` until the action timed out; the single bounded failed-job retry created the same deployment and GitHub returned `Deployment failed, try again later`. The dependent `auctiongeek.co.uk` job was skipped, so both live channels remain on the preceding successful bank. No further retry was launched against the same provider-side blocker.
- No collector, database writer or publisher remained active or queued at handoff; the banked evidence and both failed-publication checkpoints remain preserved.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`50749`](https://online.auctionhouse.co.uk/past-auctions/50749?lotResultType=All), principally dated 15 August 2023. The surviving first-party results page exposes **49 of 49** property cards with individual dates, guide, rent, tenancy, outcome and achieved-price evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 15 August 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `50749`, principally dated 15 August 2023. Source-contract commit `8924b4b4262ea746eac690e6930ece4c73b14c92`, regression commit `0e8633dfc3013a9e5cd7ebf317da7f21c4fe9187` and isolated-workflow commit `caf15f417ebf17ac54bf71a38b1b0affbe9ff343` added and exercised its strict 49-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42275548415](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42275548415) reconciled **49 of 49** visible cards and all 49 detail pages without failures. The immutable index snapshot has SHA-256 `f146e03114c3f69fd4a4aaddc46e848f6e7f771ed77181423bd8ea936ee3729b`; bank commit: `26a64fefc8e6026540ddc7f77c9f473b24aff21a`.
- Net newly banked growth after exact-overlap exclusion: **33 appearances**, **33 address records** and **33 exact-dated address records inside the current 20-year window**. Sixteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 0 land, 15 residential and 17 unknown. Detail-derived branch labels remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): North West 7, Coventry and Warwickshire 1, London 2, Wales - Cardiff 1, Sussex & Hampshire 2, Cheshire 3, North East 1, Essex & Kent 1, East Anglia 1, South West 2, South Yorkshire 1 and Scotland 11; they are not counted as new auctioneers.
- Actual new evidence: **33 guide prices**, **2 achieved sale prices** and **0 rent values**. Outcomes remain separate: 24 unsold, three sold prior, two sold, three postponed and one withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 1 to 15 August 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,980 appearances**, **300,028 address records**, **302,717 in-window appearances**, **105,055 in-window guides** and **112,135 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **151 future-dated**. Complete surviving catalogue states are **4,560**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- Publication run [42276254182](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42276254182) completed successfully for both GitHub Pages and `auctiongeek.co.uk`, including source-to-live and production property-data verification. This fresh deployment clears the preceding provider-side Pages blocker while preserving its failed-publication evidence artifacts.
- No collector, database writer or publisher remained active or queued at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`50717`](https://online.auctionhouse.co.uk/past-auctions/50717?lotResultType=All), principally dated 8 August 2023. The surviving first-party results page exposes **32 of 32** property cards with individual outcomes, guides, achieved-price, tenancy, land and mixed-use evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 8 August 2023 catalogue

- Growth opportunity executed: previously unconfigured Auction House Online event `50717`, principally dated 8 August 2023. Source-contract commit `56a24149e9e27388df14f5e64dbb1555ee41c6ec`, regression commit `8042624a2a78a33f515663c60e1a60e109084080` and isolated-workflow commit `b28df0e5a325aa00bf969bb8f9fbf950eec455d2` added and exercised its strict 32-card first-party contract. Validation passed **473 admission/identity tests** and **174 continuation/workflow tests** before collection.
- Collection run [42285384173](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42285384173) reconciled **32 of 32** visible cards and all 32 detail pages without failures. The immutable index snapshot has SHA-256 `6ffe6bd466c1291d3dca86041b2fdd8892198c3535213a6b2fe76fab784aa936`; bank commit: `df06524957280ac32dec23bfe2c0ebaf2071355b`.
- Net newly banked growth after exact-overlap exclusion: **19 appearances**, **19 address records** and **19 exact-dated address records inside the current 20-year window**. Thirteen exact date/address overlaps were excluded; duplicate source identities were **0** and no evidence was discarded.
- Net sectors: **1 commercial**, **0 mixed-use**, 4 land, 5 residential and 9 unknown. Detail-derived branch labels remain aliases of AUCTION HOUSE UK LIMITED (company 06025583): Scotland 5, Wales - Cardiff 7, Cheshire 1, West Yorkshire 3, Birmingham 1, Lincolnshire 1 and North West 1; they are not counted as new auctioneers.
- Actual new evidence: **19 guide prices**, **1 achieved sale price** and **0 rent values**. Outcomes remain separate: one sold, 13 unsold, one postponed, one sold prior and three withdrawn. Partial, undated and future-dated gains are all **0**; individual dates from 19 July to 8 August 2023 are retained.
- The event-level summary reports `new_source_years: [2023]`, but Auction House Online/2023 was already represented. This handoff therefore counts **0 genuinely new operator source-years** and one additional fully reconciled 2023 source-event.
- Rebuilt totals: **310,999 appearances**, **300,047 address records**, **302,736 in-window appearances**, **105,074 in-window guides** and **112,136 in-window achieved prices**. Remaining classifications: **10,952 partial**, **5,017 undated** and **151 future-dated**. Complete surviving catalogue states are **4,565**, incomplete/unreconciled states **556**, and fetch/parse failures **31**. National completeness remains **false**.
- A scheduled Savills bulk-history run [42278626693](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42278626693) was already active when this work began, so no data-writing collector was launched concurrently. That run was cancelled during checkout before dependencies, collection or commits. The source contract and regression assertion were prepared with skip-CI commits while its lane was occupied; the isolated collector was triggered only after all lanes cleared.
- Publication run [42286166991](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42286166991) completed successfully for both GitHub Pages and `auctiongeek.co.uk`, including source-to-live and production property-data verification.
- No collector, database writer or publisher remained active or queued at handoff.

Next concrete growth target: add a strict isolated contract for Auction House Online event [`50662`](https://online.auctionhouse.co.uk/past-auctions/50662?lotResultType=All), principally dated 1 August 2023. The surviving first-party results page exposes **69 of 69** property cards with individual dates, guides, outcomes, achieved prices, land, tenancy and mixed-use evidence, and the event is absent from the collector configuration. Preserve every detail-derived branch attribution, date, outcome, guide, achieved price, rent, original URL and immutable snapshot; exclude exact date/address overlaps before claiming growth.

## 2026-11-06 Auction House Online 1 August 2023 canonical-event recovery

- **Specific growth opportunity:** Auction House Online event `50662`, principally dated 1 August 2023, exposed 69 first-party lot cards at `https://online.auctionhouse.co.uk/past-auctions/50662`. This was selected as an uncaptured substantial catalogue, not an exhausted-archive refresh.
- **Bounded blocked route:** the initial strict contract was introduced in source commit `f85daca81e8735784f7b8666be3ad5391f67499f`, test commit `fa18bfba5ec9c86fc3953bc364a4308967e73b11`, and isolated workflow commit `ac444ca3cdba70f6bd59aad503312d333da97680`. Collection run `42293648065` made three bounded 90-second attempts against the query-form URL `/past-auctions/50662?lotResultType=All`; each read timed out before the archive index. It captured no target lots and produced no collection growth. Its failed-run artifact and the no-growth packaging checkpoint `fb7931868f2a40a7d01652d40ffef129af2c8031` remain preserved, but that checkpoint is not counted as evidence growth. Do not retry that query route without new evidence.
- **Materially different recovery:** the first-party canonical event page, without the query string, was adopted in source recovery commit `445b5186393864b3e873239a7bbca56459512fa2`, test recovery commit `ffd17f07e09043c9c1efd385e6c313f95900b000`, and workflow recovery commit `e86929463adbeeb6494984f32d1ee514ffc782cc`. Validation passed 473 admission/identity tests and 174 continuation/workflow tests.
- **Immutable evidence banked:** recovery run `42295590467` captured all 69/69 archive cards and all 69/69 detail pages with no detail failures. The immutable archive snapshot SHA-256 is `ae3d7ff002cc7bc9c5a020041827861cb8dbb2b4830b376f054ec21589d2a7ea`; rebuilt database commit `180cb3a166396f8a3e3bfcbce73b843f0cd55495` preserves source URLs, individual dates, guides, achieved prices and outcomes.
- **Measured net growth:** +53 individual appearances, +53 dated address records within the rolling 20-year window, +53 in-window appearances, +1 commercial, +0 mixed-use, +2 land, +4 residential and +46 unknown-sector appearances. Price evidence added separately: +53 guide-price records, +4 achieved sale-price records and +0 rent records. Published outcomes among the newly admitted records are 4 sold, 44 unsold, 4 postponed and 1 withdrawn.
- **Non-growth reconciliation:** 16 cards were exact date/address overlaps and were excluded from claimed growth. The bank reported 0 duplicate source identities, 0 partial records, 0 undated records and 0 future-dated records. Individual dates span 25 July to 1 August 2023. Auction House branches/trading labels (Wales-Cardiff, North West, Cheshire, Lincolnshire, South West, Coventry and Warwickshire, and Scotland) are reconciled aliases under AUCTION HOUSE UK LIMITED (company 06025583), not new auctioneers.
- **Coverage accounting:** this is one newly reconciled source-event but **0 newly covered operator source-years**, because Auction House Online/2023 was already represented. Directory entries and the catalogue page itself are not counted as properties.
- **Rebuilt corpus:** 311,052 appearances, 300,100 address records, 10,952 partial records, 302,789 in-window appearances, 105,127 in-window guide-price records and 112,140 in-window achieved-price records. Sector totals are 42,587 commercial, 19,023 land, 47,607 mixed-use, 151,054 residential and 50,781 unknown. Global undated and future-dated counts remain 5,017 and 151 respectively. Source-state totals are 4,569 complete, 556 incomplete and 31 fetch/parse failures.
- **Publication protection:** publication run `42296394401` completed successfully on both the GitHub Pages and `auctiongeek.co.uk` jobs, including source-to-live, production property-data, code and indexing verification. After completion there were no queued or in-progress workflows.
- **Next concrete growth target:** Auction House Online event `50177`, principally dated 25 July 2023, at `https://online.auctionhouse.co.uk/past-auctions/50177`. The first-party archive exposes 29/29 cards with guide and achieved-price evidence and commercial signals including hotel, garage and investment lots. Use the already-tested canonical event-page route, inventory all 29 cards, recover every detail page, and exclude exact overlaps before claiming growth.
- National completeness remains **false** until source-by-source lot inventories and genuine auctioneer coverage reconcile.



## 2026-11-06 Auction House Online 25 July 2023 and bounded continuation growth

- **Specific catalogue opportunity executed:** Auction House Online event `50177`, principally dated 25 July 2023, was absent from the retained-grid configuration but exposed 29/29 first-party cards at `https://online.auctionhouse.co.uk/past-auctions/50177`. Source-contract commit `0e4f66047c2aedc6fe9180fda83399e53026a3c2`, regression commit `a69ae0a2fcd0134227ff9e6fc1f1824f2fe14db1` and isolated-workflow commit `7fe75f3d47a8b9cf33fa1c7620c2e0ef7d59d97e` added and exercised its canonical-event route, exact overlap exclusion and bounded detail recovery.
- **Immutable event evidence banked:** collection run [42298221609](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42298221609) captured all 29/29 cards and all 29/29 detail pages with no failures. The immutable archive snapshot SHA-256 is `cfe7713424fce50dbab9514aca02622fdd8e56be039c829017ddfe2fa414c30b`; event bank commit: `b4b866073e3e89dc58b898eccc80a114b2d97834`.
- **Event-level net growth:** +10 individual appearances, +10 address records and +10 exact-dated address records/appearances inside the rolling 20-year window. Nineteen exact date/address overlaps were excluded, duplicate source identities were 0, and no evidence was discarded. Net sectors are 0 commercial, 0 mixed-use, 0 land, 6 residential and 4 unknown.
- **Event-level evidence fields:** +10 guide-price records, +1 achieved sale-price record and +0 rent records. Published outcomes remain separate: 2 postponed, 3 unsold, 1 sold prior, 3 withdrawn and 1 sold. Partial, undated and future-dated gains are all 0; retained individual dates span 19 to 25 July 2023.
- **Event attribution and coverage:** detail-derived labels Auction House Notts & Derby (2), Auction House London (4) and Auction House Wales - Cardiff (4) remain branches/trading aliases of AUCTION HOUSE UK LIMITED (company 06025583), not new auctioneers. The event adds one fully reconciled 2023 source-event but **0 genuinely new operator source-years**, because Auction House Online/2023 was already represented.
- **Protected continuation pass:** after the event bank, the repository's existing bounded continuation workflow [42299166350](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42299166350) ran without a duplicate event collector and banked a separate +7 appearances and +6 address records in commit `efca3c60fe5eebdb6bce314ab0c17af46d18f42d`. Its measured deltas are +4 dated in-window appearances, +0 commercial, +0 mixed-use, +1 land, +3 residential, +3 unknown, +0 guides, +1 achieved sale price, +1 partial, +1 undated and +2 future-dated records. No genuinely new operator source-year is claimed.
- **Continuation source accounting:** Symonds & Sampson contributed one appearance whose address/date remained unresolved; Town & Country Property Auctions contributed four addressed appearances; the Auction House National and regional passes contributed one addressed appearance each. These aggregator/regional rows retain their published auctioneer attribution and do not create new auctioneers. Existing source failures were bounded and did not prevent banking; no exhausted route was reclassified as collection growth.
- **Combined measured run growth:** +17 individual appearances, +16 address records and +14 dated in-window appearances; +0 commercial and +0 mixed-use; +10 guide-price records and +2 achieved sale-price records. Classification deltas are +1 partial, +1 undated and +2 future-dated. Event duplicates are explicitly 0; continuation duplicate counts are not inferred from aggregate deltas.
- **Rebuilt corpus:** 311,069 appearances, 300,116 address records, 10,953 partial records, 302,803 in-window appearances, 105,137 in-window guide-price records and 112,142 in-window achieved-price records. Sector totals are 42,587 commercial, 19,024 land, 47,607 mixed-use, 151,063 residential and 50,788 unknown. Global undated and future-dated totals are 5,018 and 153 respectively. Source-state totals are 4,573 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Publication protection:** the event bank first published successfully in run [42298980696](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42298980696). The continuation-triggered merged publication run [42302570619](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42302570619) then completed successfully on GitHub Pages and `auctiongeek.co.uk`, including source-to-live, production property-data, code and indexing verification. No collector, database writer or publisher was active or queued before this skip-CI handoff.
- **Next concrete growth target:** add a strict isolated contract for Auction House Online event [`49981`](https://online.auctionhouse.co.uk/past-auctions/49981), principally dated 18 July 2023. The surviving first-party event exposes 23/23 cards with individual guides and achieved-price evidence, including former-chapel and other sector signals. Use the tested canonical event-page route, capture every card and detail page, preserve branch/date/outcome/guide/achieved-price/rent/source evidence, and exclude exact overlaps before claiming growth.
- National completeness remains **false** until source-by-source lot inventories and genuine auctioneer coverage reconcile.


## 2026-11-06 Auction House Online 18 July 2023 catalogue

- **Specific growth opportunity executed:** previously unconfigured Auction House Online event `49981`, dated 18 July 2023, exposed 23/23 first-party cards at `https://online.auctionhouse.co.uk/past-auctions/49981`. Source-contract commit `a76b66b0fb474f683060a984c580e810f8a85d72`, regression commit `ebcb27c4954b7850c2de43d61c7f1226677783fc` and isolated-workflow commit `2ad0c2b6ca40f4d92379cbbd6d4e67b977a18cf7` added and exercised the canonical event route, strict visible-card denominator, detail-derived attribution and exact overlap exclusion.
- **Immutable evidence banked:** collection run [42308829850](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42308829850) captured all 23/23 cards and all 23/23 detail pages with no failures. The immutable archive snapshot SHA-256 is `bd858273a19ce3e4b07e1cf8d1e46462e65c0bb70594fe36a56d617fe83bef81`; rebuilt data commit: `36505d0316b820df29f63c7adfa1f17c18d2f832`. Validation passed 473 admission/identity tests and 174 continuation/storage tests.
- **Measured net growth:** +3 individual appearances, +3 address records and +3 exact-dated address records inside the rolling 20-year window. Net sectors are +1 commercial, +0 mixed-use, +0 land, +1 residential and +1 unknown. Price evidence added separately: +3 guide-price records, +1 achieved sale-price record and +0 rent records. Published outcomes remain distinct: 1 sold and 2 unsold.
- **Non-growth reconciliation:** 20 cards were exact date/address overlaps and were excluded from claimed growth while their original URLs and snapshots were retained. Duplicate source identities, partial records, undated records and future-dated records were all 0; every newly admitted appearance retains the individual date 18 July 2023.
- **Operator and coverage accounting:** detail-derived Auction House London (1) and Auction House Lincolnshire (2) labels remain branches/trading aliases of AUCTION HOUSE UK LIMITED (company 06025583), not new auctioneers. The event adds one fully reconciled 2023 source-event but **0 genuinely new operator source-years**, because Auction House Online/2023 was already represented.
- **Rebuilt corpus:** 311,072 appearances, 300,119 address records, 10,953 partial records, 302,806 in-window appearances, 105,140 in-window guide-price records and 112,143 in-window achieved-price records. Sector totals are 42,588 commercial, 19,024 land, 47,607 mixed-use, 151,064 residential and 50,789 unknown. Global undated and future-dated totals remain 5,018 and 153. Source-state totals are 4,574 complete, 556 incomplete/unreconciled and 31 fetch/parse failures.
- **Publication checkpoint preserved:** publication run [42309500749](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/runs/42309500749) passed tests, browser checks, export, artifact upload and property-search preservation, but GitHub Pages remained pending until `actions/deploy-pages` timed out and cancelled deployment `36505d0316b820df29f63c7adfa1f17c18d2f832`. The source-to-live reconciliation artifact remains preserved; the dependent `auctiongeek.co.uk` job was skipped, so live channels remain on the preceding successful bank. No identical retry was launched against the same provider-side route.
- **Next concrete growth target:** add a strict isolated contract for Auction House Online event [`50043`](https://online.auctionhouse.co.uk/past-auctions/50043), principally dated 11 July 2023. The surviving first-party event exposes 16/16 cards with individual dates, guides, rents, achieved prices and commercial signals including ground-floor shops. Use the tested canonical event-page route, capture every card and detail page, preserve branch/date/outcome/guide/achieved-price/rent/source evidence, and exclude exact overlaps before claiming growth.
- National completeness remains **false** until source-by-source lot inventories and genuine auctioneer coverage reconcile.
