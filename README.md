# Auction Sniper V2 Final

Commercial/mixed-use UK auction scanner.

Key corrections:
- Every scan replaces the entire current snapshot; stale lots cannot survive.
- Auction House London uses its dedicated commercial-property page only.
- Allsop uses its dedicated commercial-auctions page only.
- Pugh/BTG Eddisons and Bond Wolfe require positive commercial evidence and then re-check the exact lot page.
- Savills uses its published Commercial Section range where detectable and otherwise requires positive commercial evidence.
- Acuitus is treated as a commercial source and reports catalogue-pending state.
- No fallback/default rent figures.
- GIY is calculated only from an extracted guide and passing rent.
- Missing values remain Unknown.
