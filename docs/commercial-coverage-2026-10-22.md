# UK commercial auction coverage — 22 October 2026

## Verified results

The current published dataset contains **1,025 board records**, compared with **807** eligible records in the 21 October baseline. It retains **1,318 archived snapshot records**, compared with 1,280. These are auction records, not unique buildings or a count of properties still available to buy. Today’s sold lots can remain on the board with their result clearly labelled.

The expansion is operational, but UK-wide completeness is **not established**. Several sources remain inaccessible or partially reconciled. Directory entries, successfully parsed pages and actual commercial inventory are reported separately. The complete machine-readable evidence is in [coverage-release-2026-10-22.json](coverage-release-2026-10-22.json); the original inventory is retained in [coverage-baseline-2026-10-22.json](coverage-baseline-2026-10-22.json).

| Measure | Before | After |
|---|---:|---:|
| Current board records | 807 | 1,025 |
| Retained archive records | 1,280 | 1,318 |
| Source-health entries, including regions and aliases | 55 | 62 |
| Historical corpus appearances, all sectors | 278,349 | 278,542 |

The historical increase includes other scheduled harvesting during this work. It is not all attributable to the new collectors. The all-sector corpus includes repeated appearances and partial records; it is not proof of complete 20-year coverage.

The deployed searchable index contains 1,073 current and retained historical/unsold records. It matched the expected IDs and customer-visible facts with no missing IDs, unexpected IDs or duplicate index rows. [Whole-index verification](coverage-source-live-2026-10-22.json).

## New and repaired collection

| Source | Published current records | Archived snapshot records | What was verified |
|---|---:|---:|---|
| Knight Frank Auctions | 3 | 0 | Repaired discovery and complete 18-lot pagination; three commercial records, including one reported sold today. |
| Shepherd Commercial Auctions | 19 | 0 | 39 detail pages inspected; 19 commercial records. Whole-catalogue denominator remains unknown. |
| Prime Property Auctions | 82 | 0 | 82 commercial records. Production had two detail timeouts; no copied photographs or marketing prose. Live bids are not substituted for guides or results. |
| Hollis Morgan | 11 | 3 | All 69 particulars parsed, including garage blocks and separately offered ground rents. Eleven current offerings and three recent results. |
| Agents Property Auction | 6 | 0 | 215 unique particulars reconciled against the advertised 215. Six commercial interests; three explicitly dated 29 October and three undated ongoing offerings. |
| Greenslade Taylor Hunt | 0 | 0 | Adapter tested locally: 199 links, five historical commercial appearances, ten date failures. Production returned HTTP 403: no live ingestion claimed. |
| Maggs & Allen | 0 | 4 | Four historical commercial outcomes captured. Seven particulars without reliable auction years remain excluded. |
| Shonki Bros | 0 | 0 | Scheduled adapter inspected 16 particulars. No qualifying commercial addition established; separate from Kal Sangra Shonki Brothers. |

The reported increase also includes refreshed existing auctioneers. It must not be described as entirely new-source stock. Auction House Notts & Derby now has exact storefront-to-lot provenance: two current records are attributed to the regional brand while retaining their canonical Auction House National Online records. No duplicate lots were created to increase the regional count.

## Corrections to commercial classification

The source-to-publication comparison exposed genuine commercial investments being rejected because their particulars also mentioned flats or possible residential development. The reusable classifier now recognises existing retail areas, office suites, equestrian facilities, outdoor leisure centres, income-producing parking and numbered garage blocks. “Landmark Location” no longer causes a pub’s accommodation description to be removed as surrounding-area text. Source spelling variation in “convenience store” is handled. Full-page navigation is removed from affected particulars.

Nine fresh catalogue records were eligible for restoration, including Brentwood Leisure Park, the Railway Public House in Ryde, Vector House in Oxted, Walnut Tree Buildings, 7–9 High Street Gillingham, the Lindfield shop/maisonette, Alton car parking, and two source appearances for the Vernon Close garage block. The two garage listings are separate source IDs with undated auction records, not two proven different properties. Their source duplication/date ambiguity remains visible in the evidence.

Reclassification restoration requires an inspected current source record and a snapshot less than 14 hours old. It preserves the collection timestamp and does not revive stale inventory. Ordinary homes, flats in mixed-use buildings and completed residential conversions remain excluded. The existing whole-building/unit/legal-interest relationship safeguards, including Newbury holdouts, continue to pass.

## Complete current source-health inventory

LIVE means the collector ran successfully, not that every historic catalogue is complete. CATALOGUE PENDING can also mean an inspected mixed catalogue has no qualifying commercial lots; consult its message in the evidence JSON. DEGRADED means a recorded access, parsing or reconciliation gap. MERGED SOURCE is an alias, not additional inventory. “Unknown” means no defensible commercial denominator.

| Source | Status | Board records | Captured / source commercial scope | Historical corpus appearances | Official catalogue or source example |
|---|---|---:|---|---:|---|
| Acuitus | LIVE | 52 | 52 / 52 (100.0%) | 5,697 | [Source](https://www.acuitus.co.uk/find-a-property/?which=sales) |
| Agents Property Auction | LIVE | 6 | Unknown | 0 | [Source](https://www.agentspropertyauction.com/property-search/) |
| Allsop Commercial | LIVE | 59 | 177 / 180 (98.3%) | 44,720 | [Source](https://www.allsop.co.uk/lot-overview/freehold-city-centre-hotel-retail-and-office-investment-with-development-potential-in-liverpool/c261111-023) |
| Auction Estates | LIVE | 12 | Unknown | 2,072 | [Source](https://www.auctionestates.co.uk/property/unit-8-south-street-ilkeston-derbyshire-de75-5qe-372642) |
| Auction House Beds & Bucks | CATALOGUE PENDING | 0 | Unknown | 14 | [Source](https://www.auctionhouse.co.uk/bedsandbucks) |
| Auction House Birmingham & Black Country | LIVE | 5 | Unknown | 111 | [Source](https://www.auctionhouse.co.uk/birmingham) |
| Auction House Chesterfield & North Derbyshire | LIVE | 1 | Unknown | 1 | [Source](https://www.auctionhouse.co.uk/chesterfieldandnorthderbyshire) |
| Auction House Coventry & Warwickshire | CATALOGUE PENDING | 0 | Unknown | 152 | [Source](https://www.auctionhouse.co.uk/coventryandwarwickshire) |
| Auction House Cumbria | LIVE | 10 | Unknown | 19 | [Source](https://www.auctionhouse.co.uk/cumbria) |
| Auction House East Anglia | LIVE | 3 | Unknown | 162 | [Source](https://www.auctionhouse.co.uk/eastanglia) |
| Auction House Hull & East Yorkshire | LIVE | 1 | Unknown | 103 | [Source](https://www.auctionhouse.co.uk/hullandeastyorkshire) |
| Auction House Kent | CATALOGUE PENDING | 0 | Unknown | 105 | [Source](https://www.auctionhouse.co.uk/kent) |
| Auction House Leicestershire | LIVE | 1 | Unknown | 35 | [Source](https://www.auctionhouse.co.uk/leicestershire) |
| Auction House Lincolnshire, North Notts & South Yorks | LIVE | 9 | Unknown | 919 | [Source](https://www.auctionhouse.co.uk/lincolnshire) |
| Auction House London | LIVE | 20 | Unknown | 19,656 | [Source](https://www.auctionhouse.co.uk/london) |
| Auction House Manchester | CATALOGUE PENDING | 0 | Unknown | 71 | [Source](https://www.auctionhouse.co.uk/manchester) |
| Auction House Midlands | LIVE | 13 | Unknown | 0 | [Source](https://www.auctionhouse.co.uk/midlands) |
| Auction House National Online | LIVE | 30 | Unknown | 0 | [Source](https://www.auctionhouse.co.uk/national) |
| Auction House North East | LIVE | 2 | Unknown | 566 | [Source](https://www.auctionhouse.co.uk/northeast) |
| Auction House North West | LIVE | 15 | Unknown | 403 | [Source](https://www.auctionhouse.co.uk/northwest) |
| Auction House North Yorkshire & Tees Valley | LIVE | 2 | Unknown | 35 | [Source](https://www.auctionhouse.co.uk/teesvalley) |
| Auction House Northants, Beds & Bucks | LIVE | 1 | Unknown | 23 | [Source](https://www.auctionhouse.co.uk/northantsbedsandbucks) |
| Auction House Northern Ireland | CATALOGUE PENDING | 0 | Unknown | 6 | [Source](https://www.auctionhouse.co.uk/northernireland) |
| Auction House Oxfordshire | CATALOGUE PENDING | 0 | Unknown | 0 | [Source](https://www.auctionhouse.co.uk/oxfordshire) |
| Auction House Scotland | LIVE | 48 | Unknown | 3 | [Source](https://www.auctionhouse.co.uk/scotland) |
| Auction House South West | LIVE | 5 | Unknown | 232 | [Source](https://www.auctionhouse.co.uk/southwest) |
| Auction House South Yorkshire | LIVE | 5 | Unknown | 1,798 | [Source](https://www.auctionhouse.co.uk/southyorkshire) |
| Auction House Sussex & Hampshire | LIVE | 2 | Unknown | 39 | [Source](https://www.auctionhouse.co.uk/sussexandhampshire) |
| Auction House Wales | LIVE | 12 | Unknown | 475 | [Source](https://www.auctionhouse.co.uk/wales) |
| Auction House West Yorkshire | LIVE | 0 | Unknown | 117 | [Source](https://www.auctionhouse.co.uk/westyorkshire) |
| Barnard Marcus | DEGRADED | 2 | Unknown | 6,354 | [Source](https://www.barnardmarcusauctions.co.uk/auctions/17-november-2026/731304/) |
| Barnett Ross | LIVE | 11 | 11 / 11 (100.0%) | 7,536 | [Source](https://www.barnettross.co.uk/current.php) |
| BidX1 | LIVE | 11 | 11 / 16 (68.8%) | 294 | [Source](https://bidx1.com/en/en-gb/auction/property/109035) |
| Bond Wolfe | LIVE | 26 | Unknown | 9,407 | [Source](https://www.bondwolfe.com/order-of-sale/) |
| Cheffins | LIVE | 3 | Unknown | 740 | [Source](https://timedpropertyauctions.cheffins.co.uk/search) |
| Clive Emson | LIVE | 35 | 35 / 35 (100.0%) | 3,931 | [Source](https://www.cliveemson.co.uk/properties/269/98/) |
| Dedman Gray | MERGED SOURCE | 0 | Unknown | 2,851 | Source link not retained in telemetry |
| Edward Mellor | LIVE | 6 | Unknown | 10,065 | [Source](https://edwardmellor.co.uk/property-for-sale/10170772/) |
| Future Property Auctions Scotland | LIVE | 220 | Unknown | 64,584 | [Source](https://www.futurepropertyauctions.co.uk/property_details.asp?id=14522743) |
| Greenslade Taylor Hunt | DEGRADED | 0 | Unknown | 0 | [Source](https://www.gth.net/properties/sales/tag-auction) |
| Harman Healy | LIVE | 1 | Unknown | 1,507 | [Source](https://harman-healy.co.uk/lot/details/16afd78e-db0a-4625-b8ea-83e6b127c145) |
| Hollis Morgan | LIVE | 11 | Unknown | 813 | [Source](https://www.hollismorgan.co.uk/search-auction/?bid=11&showstc=on&orderby=lot_no+asc&extra_2%21=501%2C502) |
| Knight Frank Auctions | LIVE | 3 | 3 / 3 (100.0%) | 285 | [Source](https://www.knightfrankauctions.com/auction/3838/knight-frank-auctions-2026-10-22/) |
| LSH Auctions | LIVE | 8 | Unknown | 590 | [Source](https://propertyauctions.lsh.co.uk/lot/details/7510d03f-3f77-41ed-85b6-a84f01d79ed2) |
| Maggs & Allen | DEGRADED | 0 | Unknown | 108 | [Source](https://www.maggsandallen.co.uk/search-auction/) |
| McHugh & Co | DEGRADED | 0 | Unknown | 13,926 | [Source](https://www.mchughandco.com/lot/details/ee5c38c7-c894-4360-ac71-955124b366e4) |
| Network Auctions | MERGED SOURCE | 0 | Unknown | 1,202 | [Source](https://www.btgeddisonspropertyauctions.com/our-acquisitions/network-auctions) |
| Pattinson Auction | LIVE | 12 | Unknown | 0 | [Source](https://www.rightmove.co.uk/properties/87458415#/?channel=COM_BUY) |
| Paul Fosh Auctions | CATALOGUE PENDING | 0 | Unknown | 5,603 | [Source](https://auction.paulfosh.com/lot/details/56975051-9db2-4568-bb14-51aac1975acf) |
| Prime Property Auctions | DEGRADED | 82 | Unknown | 0 | [Source](https://bid.primepropertyauctions.co.uk/Event/Details/18743274/Timed-Online-Auction-22nd-October-2026) |
| Pugh / BTG Eddisons | LIVE | 86 | Unknown | 9,581 | [Source](https://www.pugh-auctions.com/property-search) |
| SDL Property Auctions | MERGED SOURCE | 0 | Unknown | 443 | [Source](https://www.eddisons.com/agency-and-auctions/property-auctions) |
| Savills Auctions | LIVE | 56 | 59 / 63 (93.7%) | 30,926 | [Source](https://auctions.savills.co.uk/auctions/3-november-2026-245) |
| Shepherd Commercial Auctions | LIVE | 19 | Unknown | 0 | [Source](https://www.shepherd.co.uk/auctions/auctions-search/) |
| Shonki Bros | LIVE | 0 | Unknown | 0 | [Source](https://www.shonkibros.com/auctions/latest-auctions/view) |
| Strettons | DEGRADED | 20 | Unknown | 123 | [Source](https://www.strettons.co.uk/auction-commercial-property-for-sale/commercial-property-for-sale-in-39-highbridge-street-waltham-abbey-essex-en9-1bd-6ac4e33dd181475b15ac2347) |
| Sutton Kersh | LIVE | 6 | Unknown | 11,401 | [Source](https://www.suttonkersh.co.uk/properties/lot/372589/) |
| Symonds & Sampson | LIVE | 5 | Unknown | 215 | [Source](https://auctions.symondsandsampson.co.uk/property/dwr0007f7/dt9/sherborne/street-lane/other/studio) |
| Town & Country Property Auctions | LIVE | 14 | Unknown | 2,822 | [Source](https://south.townandcountrypropertyauctions.co.uk/lot/details/c954550d-8f6d-4fdc-80d2-a2a3025e8952) |
| Under The Hammer | DEGRADED | 0 | Unknown | 0 | [Source](https://www.underthehammer.com/for-auction/properties) |
| Wilsons Property Auctions | CATALOGUE PENDING | 0 | Unknown | 0 | [Source](https://www.wilsonsauctions.com/auctions/land-property-auctions) |
| iamsold | DEGRADED | 117 | Unknown | 0 | [Source](https://www.iamsold.co.uk/properties/) |

Where a measured source scope is below 100%, the linked evidence lists the exact unpublished URLs. Some are correctly excluded residential or unproven land interests; others have unresolved dates or collection gaps. These are not interchangeable explanations. A measured 100% applies only to that explicitly inspected catalogue scope, never to an auctioneer’s complete history or national coverage.

## Historical records and evidence

- Cottons: 83 new September/October result appearances, taking its corpus from 7,283 to 7,366. All 83 now have independently extracted catalogue guide prices with source PDF URL, page and hash evidence. Sale prices and guides remain separate.
- The scheduled historical job committed the source evidence successfully. Twelve result sheets remain pending; the September 2023 missing source and February 2018 image/OCR issue remain recorded.
- The permanent published-history workflow completed after the expanded snapshot was published. This banks new source appearances separately from the larger historical-corpus totals above.
- Source outcomes remain auctioneer-reported outcomes. They are not represented as independently confirmed completed transactions.
- Rebranded and shared feeds retain historical auctioneer identities. Exact property histories remain distinct from related freeholds, units and newly created leasehold interests; altered accommodation or interests prevent misleading price-drop calculations.

## Live property verification

Public HTTP responses, rendered property addresses, canonical URLs and Open Graph URLs were checked for these examples. Indexing eligibility still depends on sufficient property content and reliable dates. Premium history remains protected.

| Source | Property | HTTP | Public page |
|---|---|---:|---|
| Knight Frank Auctions | 11 Latimer Road, North Kensington, London, W10 6RQ | 200 | [View property](https://auctiongeek.co.uk/property/be3f932be9f0a3c54039/11-latimer-road-north-kensington-london-w10-6rq/) |
| Shepherd Commercial Auctions | 2-4 High Street, Paisley, Renfrewshire | 200 | [View property](https://auctiongeek.co.uk/property/929d756bdd6fa9358d16/2-4-high-street-paisley-renfrewshire/) |
| Prime Property Auctions | 10 Main Street, Dalry, KA24 5DH | 200 | [View property](https://auctiongeek.co.uk/property/dc71768cf2b86d0f050e/10-main-street-dalry-ka24-5dh/) |
| Hollis Morgan | 7 The Bridge, Chippenham, SN15 1HA | 200 | [View property](https://auctiongeek.co.uk/property/f2bf52290c0836327a11/7-the-bridge-chippenham-sn15-1ha/) |
| Agents Property Auction | Flats 1, 2, 3, 4, 5 Forest Villas, Newcastle Upon Tyne , NE12 9AJ | 200 | [View property](https://auctiongeek.co.uk/property/26f0eeae3a006f9d9fe8/flats-1-2-3-4-5-forest-villas-newcastle-upon-tyne-ne12-9aj/) |
| Maggs & Allen | 15-17, High Street, Kingswood, Bristol, BS15 4AA | 200 | [View property](https://auctiongeek.co.uk/property/b6637241bc76f2d8f1ad/15-17-high-street-kingswood-bristol-bs15-4aa/) |
| Savills Auctions | Brentwood Leisure Park, Brentwood, Essex CM13 3DP | 200 | [View property](https://auctiongeek.co.uk/property/c6c4453d24bdd2c4a39e/brentwood-leisure-park-brentwood-essex-cm13-3dp/) |
| Clive Emson | The Railway Public House, 68 St. Johns Road, Ryde, Isle Of Wight, PO33 2RT | 200 | [View property](https://auctiongeek.co.uk/property/6501874c57e1755d8d10/the-railway-public-house-68-st-johns-road-ryde-isle-of-wight-po33-2rt/) |
| Savills Auctions | Car Park Bakers Alley, High Street, Alton, Hampshire, GU34 1BD | 200 | [View property](https://auctiongeek.co.uk/property/8342f0c08817b48e4892/car-park-bakers-alley-high-street-alton-hampshire-gu34-1bd/) |

## Coverage dashboard and reliability

The owner interface reports comparable official/captured lots, missing URLs, duplicates, last successful collection, source errors, historical holdings and reported-outcome coverage. Unknown or invalid dates cannot be treated as past results or crash the dashboard. No coverage percentage is invented when the denominator is unknown. Anonymous requests to the owner API are rejected with HTTP 401. Deployed interface code and authenticated browser contracts were checked; an owner-signed-in inspection of the live dashboard was not performed.

Current collection and historical harvesting run every six hours. Freshness checks run hourly and retain source-level failures. Existing stock is preserved during temporary outages with explicit stale-source rules. The production scanner and public build now use Ubuntu 24.04, with bounded dependency setup; an earlier stalled run was cancelled before collection. [Cancellation evidence](coverage-evidence/cancelled-stalled-run-20261022.jpg).

Final regression verification: **1,466 tests passed, 14 skipped, plus 22 subtests**. Subsequent targeted checks for historical-label totals, source headings and free snapshots also passed (28 checks in the final targeted run). The restored snapshot passed the unchanged publication gate. Account/coverage browser checks passed at 360, 390, 430 and 1,440-pixel widths. No paid AI generation, paid data subscription or advertising was added.

## Outstanding work and access limitations

1. **Bradley Hall, Landwood, Goldings and First for Auctions:** direct catalogue access returned HTTP 403. A permitted accessible feed is still required. A 403 alone does not establish that a paid licence is necessary. Bradley Hall’s [7 Norfolk Street, Sunderland](https://auction.bradleyhall.co.uk/lot/details/03059dab-f2ca-4629-9b41-55cadfe7fc3d) (£199,000 guide) and [1 Hartington Street, Consett](https://auction.bradleyhall.co.uk/lot/details/8ac22c9b-4136-44e4-8d85-3d6ba5ae28bd) (£145,000 guide), both advertised for 28 October, demonstrate actual commercial coverage gaps.
2. **GTH:** resolve production access before claiming live integration. Local parser success does not override the production 403.
3. **Brown & Co and Kivells:** five accessible Brown livestream particulars and 27 Kivells particulars did not establish qualifying current commercial stock. Brown’s linked online EIG catalogue was inaccessible. Automated monitoring/ingestion remains incomplete.
4. **Existing-source gaps:** Strettons’ current index yielded no detail links in this run, so 20 eligible known records were retained. McHugh’s next catalogue could not be resolved; Under The Hammer returned 403. Barnard Marcus had three detail failures. iamsold had pagination/detail gaps despite the repaired factual extraction. Prime had two timeouts. These sources are not all being labelled healthy.
5. **Evidence gaps:** seven Maggs particulars lack auction years; GTH has ten date failures locally. BidX1 includes undated and duplicate source appearances. One Savills Rhyl URL advertises November while its extracted offered-date evidence remains September; it needs source-date reconciliation. No date is silently invented to improve counts.
6. **Completeness:** independent commercial denominators are still unavailable for many mixed catalogues. LSH, Paul Fosh, Pattinson and other sources require further catalogue reconciliation. The source inventory is complete for the configured pipeline, but the requested independent full-catalogue audit is not complete for every operator.
7. **History:** comprehensive 20-year coverage and comprehensive future Cottons catalogue/tenancy ingestion remain unfinished. Existing schedules continue harvesting available evidence; they do not guarantee inaccessible or missing catalogues can be recovered.
8. **Rights and SEO:** Prime supplies factual summaries without copied photographs or marketing text. Some sparse or undated pages appropriately remain noindex. No paid licence, AI research or advertising has been introduced to fill missing facts.
