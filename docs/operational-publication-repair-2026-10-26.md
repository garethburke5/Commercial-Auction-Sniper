# Operational publication repair — 26 October 2026

The permanent published-lot history had 87,147 property-index rows but only
23,116 distinct property IDs. Repeated banking of known events with missing
postcodes created duplicate index entries. Updates now retain existing event
identities and consolidate only identical property IDs, preserving all address
variants, event references and observation date bounds. Distinct IDs remain separate.

A production replay reduced the file from 104,580,910 to 61,260,803 bytes.
All 27,085 auction events were exactly unchanged. Every property ID, address
variant and event reference survived. This is separate from the national
historical-appearance corpus. Compact atomic JSON retains existing reader
compatibility. Banking validates uniqueness, references, evidence URLs, counts
and size; warns at 80 MiB; and refuses replacement at 95 MiB. It rebuilds on
the newest main branch when publication races occur. Current headroom is
approximately 41.6 MiB; this is not unlimited single-file capacity.

Sutton Kersh lots 69 and 70 are ordinary houses. A guide-price addendum before
`Joint Agent: Logic Estate Agents` defeated an agency-credit filter anchored
to the start of the description. The filter now excludes these credits wherever
they occur, while retaining actual estate-agent premises. The failed 26 October
10:54 UTC production candidate revalidates to 991 listings: six eligible Sutton
Kersh lots, 100% images and 66.7% rich particulars. The 60% gate is unchanged.

Revalidation can recover newer fresh candidate artifacts only from this
repository's main-branch production workflows and ancestor commits. Collection
timestamps are preserved. Normal quality and freshness checks remain mandatory.

Local verification: 33 targeted tests passed, production history preservation
checks passed, and the recovered production candidate passed the complete
publication gate and freshness check. GitHub workflow and live confirmation
are pending deployment; local tests alone do not establish those outcomes.
