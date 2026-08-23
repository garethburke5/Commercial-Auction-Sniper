# Commercial Auction Sniper

UK commercial and mixed-use auction intelligence.

This build deliberately keeps the Python application files at repository root for easy mobile maintenance.

Current live collectors:
- Auction House London
- Pugh / BTG Eddisons
- Savills Auctions
- Allsop Commercial
- Acuitus

Core data captured where available:
- Main image
- Direct lot URL
- Address/postcode
- Guide price
- Passing rent
- Gross initial yield
- Freehold/leasehold
- VAT status
- TOGC mention
- Legal-pack availability
- Auction status
- 10% yield ceiling

The data model also reserves fields for location/pitch scoring, relettability, tenant/lease scoring, comparables, rates, service charge, EPC and target/max prices.

Unknown information remains UNKNOWN rather than being guessed.
