# Auction Sniper V4

Architecture:
1. GitHub Actions scans auction sources every 6 hours.
2. Source-specific collectors write one verified snapshot to `data/properties.json`.
3. Streamlit only reads the snapshot; it does not scrape auction sites.
4. Default view shows ALL current commercial/mixed-use properties.
5. Price/yield filters are optional and OFF by default.
6. Failed sources preserve the previous successful source data and mark those lots stale.
7. Old/pending catalogues are not presented as current auctions.

Manual run:
- GitHub -> Actions -> Auction Sniper Scan -> Run workflow.

Savills credentials:
- Repository Settings -> Secrets and variables -> Actions
- Add `SAVILLS_EMAIL`
- Add `SAVILLS_PASSWORD`

The credentials are reserved for legal-document authentication. Public lot discovery does not depend on them.
