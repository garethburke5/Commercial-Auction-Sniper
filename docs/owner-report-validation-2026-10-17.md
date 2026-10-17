# Private report validation — 17 October 2026

The owner entered the OpenAI key directly into Render. Deployment
`dep-db9vncfavr4c73fjm5rg` became live; public readiness then reported the analysis
provider configured, with paid reports unapproved and live billing disabled.
Configuration presence is not provider authentication or report acceptance.

## Private validation path

Commit `2702d5588425a2177d8527b30c76fd2a745cd2b2` adds an owner-only route for a
confirmed, scope-accepted, unpaid snapshot. It invokes the same processing,
research, reasoning, evidence checks and renderers as customer reports. There is
no property-specific narrative or alternative analysis engine. It records all
attempts and provider usage; one validation at a time, three attempts per hour
and three per report. Diagnostic output remains available to the owning owner
when automatic quality checks require review. It cannot consume credits, become
a purchased report, or grant customer access. Revoking owner status removes
private diagnostic access. Provider errors use safe categories, never raw bodies
or credentials. 84 targeted processing, entitlement, intake, provider and page
checks passed locally; one existing dependency deprecation warning remains.

## Live intake failure and memory correction

The first Newbury intake failed before an AI investigation. Render reported an
OOM kill at the 512 MiB service limit (event `evt-db9vu868bjmc73dab520`). Memory
rose from about 152 MiB to 460 MiB before the process restarted. The code fully
expanded a 95.3 MiB gzip history file into an 836.72 MiB byte buffer and loaded
all historical property JSON into memory. The observations JSON is 80.65 MiB.

The fix streams the database to its disposable query file, parses observation
events incrementally, retains compact observations and historical row references,
and hydrates matching records on demand. Comparable selection retains only the
best distinct addresses; full source records remain on disk. The canonical data
is unchanged. With the real corpus, the revised Site + Newbury market lookup
peaked at 141.5 MiB RSS and the market lookup took 5.22 seconds locally, returning
four comparable candidates. Thirteen existing matching, income chronology and
history-export checks passed. This is a local resource measurement, not yet a
successful production report.

## Acceptance still required

Run Newbury without a pack, then with the original documents, and a materially
different property through production. Inspect the actual findings, source
identity, EPC/listed/lease interactions, rental and comparable evidence, output
presentation and complete usage/costs. Preserve unknown costs as unknown. Keep
paid reports closed until both report pathways pass independent output review
and the owner approves launch. A successful private specimen does not validate
paid purchase/credit, download and post-membership entitlement journeys.
