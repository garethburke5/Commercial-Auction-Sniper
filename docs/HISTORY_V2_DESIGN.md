# Auction Sniper History V2 — site-first architecture

## Goal
Historical collection exists to answer a current-lot question instantly: **has this physical property appeared at auction before, what happened, and where is the evidence?** Collectors must emit a canonical contract that the site can consume without source-specific logic.

## Data flow
`auctioneer source -> raw source archive -> canonical auction_event -> physical property resolver -> site history index -> current lot card/history view`

Raw source payloads are evidence/reprocessing inputs. The Streamlit UI never reads them directly.

## Canonical entities

### property
One physical asset, independent of auctioneer or auction event.

Required:
- `property_id` stable internal ID
- `canonical_address`
- `postcode_normalized`
- `building_tokens`
- `street_normalized`
- `address_variants[]`
- `first_seen`, `last_seen`
- `auction_event_ids[]`

Optional: title/unit hints, lat/lon when independently available.

### auction_event
One appearance of a property in one auction.

Required:
- `event_id`
- `property_id`
- `source` / auctioneer
- `source_id`
- `auction_id`
- `auction_date`
- `lot_number`
- `address_as_published`
- `status`
- `captured_at`, `last_seen`
- `match_confidence`
- `evidence`

Commercial facts where available:
- `guide_price`, `guide_price_lower`, `guide_price_upper`, `guide_price_text`
- `sale_price`
- `annual_rent`
- `gross_yield`, `net_yield`
- `tenure`
- `tenant`
- `lease_term`, `lease_start`, `lease_expiry`, `break_date`
- `occupation`
- `property_type`
- `area_sqft`
- `description`
- `image_url`

### evidence
Every event carries source provenance where available:
- `listing_url`
- `auction_url`
- `results_url`
- `legal_pack_url`
- `source_id`
- `captured_at`
- `source_snapshot_ref` (optional future preserved snapshot)

No historic fact should be presented as verified without provenance. Missing evidence is explicit, never fabricated.

### observations
Material changes to an event are append-only observations (guide change, sold prior, sale result, rent/tenancy change). This preserves the lifecycle rather than overwriting it.

## Property resolution
Matching is conservative.

1. Exact normalized postcode + compatible building/unit identity = high confidence.
2. Building name/number + strong street/address similarity can produce probable match.
3. Conflicting building numbers at the same postcode must not auto-merge.
4. `6`, `6A`, `6-8`, `Ground Floor 6`, and multi-title/unit cases require unit/range-aware rules.
5. Store `match_confidence` and `match_reason`.

UI classes:
- `EXACT` / `HIGH`: automatically shown as previous history.
- `PROBABLE`: shown with a match-confidence indication.
- `POSSIBLE_RELATED`: separate "Possible related history" section; never silently merged.

## Site-facing index
The site should not scan all historical events per card. Build a compact `history_index.json` keyed primarily by normalized postcode, then building/unit tokens, pointing to `property_id` and event IDs. Current lots resolve against the index when the production dataset is built/refreshed.

For each current lot, produce a lightweight history summary:
- `history_count`
- `previous_sale_count`
- `latest_previous_event_id`
- `latest_previous_sale_price`
- `latest_previous_sale_date`
- `history_match_level`
- `history_event_ids[]`

This lets the grid render cheaply; full event details are loaded only when history is opened.

## UI behaviour
Replace the current Google-first `Previous auctions / sale history` action.

- If internal matches exist: open an Auction Sniper history view/panel.
- Show events newest-first with auctioneer, date, lot, guide, result/sale price, rent, yield, tenure and tenant/lease facts when available.
- Each event exposes `View auction evidence` links for available listing/results/auction/legal-pack sources.
- Show useful deltas where possible: previous sale -> current guide; previous rent -> current rent; yield movement.
- Clearly label exact/probable/possible-related matching.
- Retain `Search web for more history` as a secondary fallback, especially when no internal match exists.

## Collector contract
Every source adapter (Allsop, Savills, Strettons, SDL/Pugh/BTG, Auction House, Acuitus, Barnard Marcus, Clive Emson, Bond Wolfe, etc.) may collect different raw fields but must normalize to this contract before production import.

Completeness telemetry per source must include:
- discovered/completed auction IDs
- expected vs captured lot counts where source supplies totals
- earliest/latest dates
- remaining count
- failures/retries
- evidence-link coverage
- last successful capture/import timestamp

## Allsop migration
The completed Allsop source archive (100 discovered commercial auctions / 13,792 captured lots / Feb 2012–Jul 2026) is the production test set.

Migration sequence:
1. Transform Allsop rows into canonical events without recollecting.
2. Preserve result-page/lot evidence URLs and source IDs.
3. Promote `sale_price` to a first-class canonical field.
4. Resolve events into physical properties.
5. Generate site index and current-lot history summaries.
6. Test known repeated properties end-to-end in Streamlit.
7. Only after this contract is proven, feed Savills/Strettons and other archives through the same pipeline.

## Storage boundary
Initial zero-cost implementation can remain versioned JSON in the private production repo:
- `data/property_history.json` — canonical properties + events
- `data/history_index.json` — compact lookup index
- `data/historical_backfill_progress.json` — source/import telemetry

The schema deliberately separates storage from UI so it can later move to SQLite/Postgres/object storage without changing the collector contract or site semantics.

## Acceptance tests
History V2 is not complete until:
1. 13,792 Allsop source rows are accounted for by import telemetry (with explicit rejection/quarantine counts if any).
2. No event without an address/source/evidence identity is silently accepted.
3. Duplicate re-import is idempotent.
4. A known current property with Allsop history displays the correct previous event inside Auction Sniper.
5. Evidence link opens the corresponding auctioneer evidence where still available.
6. A same-postcode neighbouring property does not false-match.
7. A unit/range ambiguity is downgraded rather than silently merged.
8. Google/web search remains only the fallback, not the primary history implementation.
