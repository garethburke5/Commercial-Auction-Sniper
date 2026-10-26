# Cloudflare build allowance recovery — 26 October 2026

## Confirmed cause
The owner's Cloudflare screenshot shows all 3,000 included monthly Workers Build
minutes consumed. Builds are paused until 31 October 2026, 23:59 GMT.
The existing deployment remains live. Being signed out does not cause this.

Last successful check before the failure sequence: commit
7b71de82aa57ecaa9b6973bd1e74bf0a606a69f6, completed 02:26 UTC.
The next commit, 4096f1478a2a9f2080768959cb33c25d34c71069, failed at
03:11 UTC. It changed collection checkpoint/source records and documentation,
not the website or deployment configuration. GitHub check timestamps have equal
start/end values for successful builds too; they cannot establish build duration.

## Implemented recovery
Public platform foundation retains its test, browser and GitHub Pages checks.
A following Cloudflare job checks out the exact tested revision, builds separately
for https://auctiongeek.co.uk, checks the static asset limits, runs a pinned
Wrangler 4.153.0 dry run, then uploads to the existing auction-geek Worker.
It does not call Cloudflare Workers Builds.

The production build must never reuse the GitHub Pages export: that copy uses
a project subpath and intentionally carries noindex. Production uses the existing
Cloudflare renderer and existing repository public configuration variables.

The deployment token is available only to the deployment step, never to renderer,
tests or public files. Missing credentials fail explicitly after packaging.
Post-deploy checks compare live properties and public configuration, require the
tested code revision marker, and reject a wrong canonical host or noindex homepage.
The job has only contents:read GitHub permissions.

## One-time credential setup
In Cloudflare's API Tokens page create a custom deployment token, named
Auction Geek GitHub deployment. Scope it to the existing Auction Geek account:
- Account / Workers Scripts / Edit.
- Zone / Workers Routes / Edit, restricted to auctiongeek.co.uk.
- Zone / Zone / Read, restricted to auctiongeek.co.uk.

Do not grant account-wide DNS editing, storage, billing, or unrelated zone access.
Where the newer per-Worker roles UI is offered, use Editor on auction-geek with
the zone route permission for auctiongeek.co.uk.

Copy the token directly into this repository's Settings > Secrets and variables >
Actions > New repository secret, named CLOUDFLARE_API_TOKEN.
Never paste the token into chat, source code or workflow logs.
The non-secret account ID is already configured in the workflow.

Then rerun the failed Deploy auctiongeek.co.uk job in Public platform foundation.
A successful GitHub Pages job alone is not evidence of production publication.
Production completion requires the Cloudflare deploy and both live verification
steps to pass.

## Stop the duplicate Cloudflare builds
Disable automatic Git builds for auction-geek in Cloudflare Settings > Build.
Do not delete the Worker, remove the custom domain, or change DNS.
Do this before the monthly allowance resets, so the old Git integration cannot
deploy an older queued build over the new pipeline.

GitHub publication remains triggered by selected website code changes and successful
publication/history/gallery workflows, not every raw data/checkpoint/docs commit.
A manual workflow dispatch remains available. Existing workflow concurrency serializes
publication and checks out current main at the beginning, then pins both exports
to the same tested commit. Collection itself continues independently.

Pause production publishing by removing/revoking this deployment token if urgently
needed. No paid Cloudflare plan or other paid service is enabled by this change.

## Validation
27 focused Cloudflare packaging, release verification and property SEO tests passed.
Tests reject stale code, wrong canonicals, noindex headers/meta, missing sitemap
advertisement and mismatched public configuration.
Workflow YAML parsed and tested-revision dependency checked locally.
Remote full tests, dry run and live deployment status must be checked separately.

## Live recovery verified — 26 October 2026, 17:10 GMT

The owner created a scoped Cloudflare token and saved the repository secret.
Run 40358749135, retry deployment job 121721357241, completed successfully.
The pipeline's public/browser suite passed 498 tests plus 3 subtests (14 skipped).
The production export passed Wrangler's dry run and uploaded 4,877 changed files
(1,614 unchanged), deploying the existing custom domain.
Cloudflare version: 13ff62fc-d65c-465e-9828-8f9f80ada28d.
Verified live code commit: f9904fc39240822ddda8437eb9929e48b270d4ae.

Both production checks passed:
- 1,075 expected searchable properties matched 1,075 live entries and checked facts.
- Exact code revision, production canonical URL, absence of homepage noindex,
  sitemap advertisement and public account/billing configuration matched the build.

The 37 degraded collection sources remain a separate coverage issue; deployment
success is not nationwide completeness or paid-report acceptance.

Disabling the old automatic Cloudflare Git builds is still unverified. The owner
has been instructed to turn those off so they do not restart when the allowance
resets. No credentials were printed or saved in source.
