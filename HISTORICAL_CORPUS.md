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
python scripts/harvest_barnett_ross_canonical.py --all-incomplete
python scripts/harvest_auction_house_northeast.py
python scripts/harvest_auction_house_south_yorkshire.py
python scripts/harvest_auction_house_north_west.py
python scripts/harvest_auction_house_south_west.py
python scripts/harvest_auction_house_east_anglia.py
python scripts/harvest_auction_house_national.py
python scripts/harvest_auction_house_regions.py
python scripts/harvest_bidx1_canonical.py
python scripts/harvest_btg_eddisons_catalogues.py 4
python scripts/harvest_sdl_legacy_catalogues.py --limit 10
python scripts/harvest_anderson_garland_results.py
python scripts/harvest_edward_mellor_results.py --limit 24 --workers 8
python scripts/harvest_future_property_auctions.py --limit 4 --workers 3
python scripts/harvest_town_country_results.py --workers 4
python scripts/harvest_brown_co_results.py
python scripts/harvest_bagshaws_results.py
python scripts/harvest_cottons_results.py 16 4
python historical_corpus.py build
```

The first command banks every lot already recovered in the Savills legacy
catalogue map, including residential lots. Missing street addresses remain null.
The second traverses all previously identified modern catalogue IDs and every
page, retaining the lot-level structured data embedded in the public website.
Run `harvest-savills --ids 241 --refresh` to recheck one auction.

Paul Fosh collection traverses and reconciles the entire paginated public results
set, retaining all addresses, published lot end dates, outcomes, prices and detail
links. Its lot end dates are labelled as such; they are not silently assumed to
be a separate catalogue's date. Listing UUIDs preserve stable source identity.

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

SDL Property Auctions collection traverses the retained first-party catalogue
archive from May 2022 through November 2025, before the BTG-era Eddisons
collector begins. Only featured cards with an exact catalogue date, stable SDL
property ID, lot number, postcode-bearing address and guide price are admitted.
Raw archive and catalogue HTML are preserved. These surviving featured subsets
never count as complete auctions because their original catalogue denominators
and non-featured rows are no longer exposed.

Anderson & Garland collection preserves every sold-property block on its
first-party recent-results page, including address text, description, image,
guide and sale price. The page is curated rather than a dated catalogue: exact
auction dates remain null and the records are explicitly excluded from complete
catalogue counts. Rex listing IDs provide identity where retained; otherwise an
exact source-heading hash is used without merging across other auctioneers.

Edward Mellor collection discovers retained first-party result pages from the auction archive and resumes through up to 24 previously uncaptured catalogues per run. Every visible card is preserved by exact auction slug, lot number and stable property ID. Retained detail pages may add the full address, tenure, images and the exact lot-level auction date only when the property ID and lot number reconcile. Two-day headings remain a date range rather than an invented lot date, and catalogues remain incomplete when the original offered denominator is unpublished.\n\nTown & Country Property Auctions collection traverses all pages of the
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
compressed source PDFs are retained for provenance. Image-only PDFs are OCRed from those saved snapshots in bounded groups of four; failed OCR is quarantined after one attempt rather than probed repeatedly.

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

The Historical lot corpus collection workflow resumes incomplete known Savills
catalogues every six hours and saves checkpoints to the repository. Its separate
output paths avoid collisions with live-board scans. Modern completed auctions
can be refreshed explicitly. The broader operation must next recover missing
legacy street addresses, revisit missing years/sources, import and validate other
auctioneers' existing raw lots, and add adapters for all recoverable UK sources.
The operation is not complete merely because currently known URLs are exhausted.
