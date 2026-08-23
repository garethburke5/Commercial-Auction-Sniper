# Auction Sniper V2

Commercial/mixed-use UK auction scanner.

V2 design principles:
- Current snapshot replaces the old database every scan: stale lots cannot survive.
- Auction House London uses its dedicated commercial page.
- Allsop uses its dedicated commercial catalogue.
- Savills detects its published Commercial Section range where available.
- Pugh and Bond Wolfe require positive commercial evidence and re-check the exact lot page.
- Acuitus is inherently commercial and reports catalogue-pending state.
- Guide/rent/yield are never filled with fallback/default values.
- GIY is calculated only from an extracted guide and passing rent.
- Unknown values remain Unknown.
