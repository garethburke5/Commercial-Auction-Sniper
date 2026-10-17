# Withdrawn catalogue visibility — 17 October 2026

Owner requirement: withdrawn properties must remain discoverable on Auction Geek, including after their auction date. The headline count must include them.

Changes:
- Main search includes captured WITHDRAWN and WITHDRAWN PRIOR records from the snapshot archive across auctioneers, without a date cutoff. Existing publication quality and commercial/mixed-use checks still apply.
- Original identities, URLs, source status and auction dates are retained. Cards and property pages use the existing status labels.
- Available results appear before unavailable results in the default catalogue ordering. Available-only search and available-lot metrics exclude withdrawn records.
- The headline is total catalogue lots; separate metrics show available, sold/withdrawn/postponed and auction houses. Mobile metrics use two columns.
- Withdrawn records missing from a later authoritative catalogue remain retained rather than being pruned. A newly observed status for the same record still takes precedence.
- Withdrawn properties are excluded from commercial deal spotlights. Past withdrawn dates do not enter the upcoming-auction strip.
- Live-index acceptance now includes retained withdrawals in its expected set.

Verification: 33 focused tests passed, including a real renderer/index/search-filter regression and collection/finalization retention test. Production publication and browser acceptance remain pending at commit time. This does not claim recovery of previously deleted records or all historical lots.
