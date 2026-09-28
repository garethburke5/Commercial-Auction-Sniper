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
