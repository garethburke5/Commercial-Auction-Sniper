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

## Verified deployment checkpoint

- Repair commits: `43de2f1fc68c3c96b9693d2c3c7f8b4930ed5563` and
  `72b3d3a86f483010720f1ff455fd5ce50aa614f3`.
- Bank Published Auction History run `40317946736` succeeded; commit
  `44607e90ec48b986119147750f0e895a354f554b` published 61,261,986 bytes.
- A second banking run, `40318862205`, also succeeded after fresh data arrived:
  23,284 property IDs, 27,374 events, 62,500,538 bytes, zero duplicate index rows.
  It added 289 events and 168 property IDs without repeating the growth defect.
- Revalidation run `40318073480` passed 1,246 tests plus 22 subtests, recovered
  the 10:54 production candidate, passed publication/freshness checks and pushed
  `01636fbb075fd2837c2d23b598c1a8baa1e3c067`. Run `40318229009` also succeeded.
- Full fresh collection run `40317946733` succeeded. Sutton Kersh collected six
  eligible lots and reconciled 6/6. Its 12:14 UTC snapshot passed publication
  and freshness checks and was committed as
  `8b3acedf43f1be30fc47e50374775e88f9b3c155`. No quality threshold was lowered.
- Public platform foundation run `40318862180` succeeded, including browser
  checks and source-to-GitHub-Pages verification (1,050 searchable properties
  for that earlier candidate; source degradation remains explicitly reported).
- The custom domain is a separate Cloudflare Workers deployment. Its build
  checks still fail immediately, without a reason in the GitHub check output.
  Direct browser inspection still showed the 23 October snapshot. Cloudflare
  required authentication; the owner's GitHub sign-in choice returned
  "Unable to sign in. Try again or use your email and password." No automated
  login retries or credential handling outside secure browser authentication.
  Custom-domain deployment remains blocked pending dashboard access/diagnosis.

The original history push and Sutton Kersh publication failures are resolved.
Do not describe the custom domain as updated until Cloudflare deployment and
source-to-live verification succeed. The temporary evidence-capture workflow
has been removed; existing production workflows perform the ongoing checks.
