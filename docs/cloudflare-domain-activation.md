# Auction Geek domain activation

Prepared 10 October 2026. The owner authorised connecting `auctiongeek.co.uk`,
purchased through Cloudflare. This is a hosting/domain task, not paid-launch approval.

**23:10 correction:** Use **Workers Static Assets** for this new deployment.
Cloudflare now explicitly recommends Workers for new projects and directs new
features and optimisations there. The initially prepared Pages route is superseded.
The same static exporter and safety checks are reused; `wrangler.jsonc` declares
only `public-dist` as assets, with canonical trailing slashes and real 404 pages.
No Worker script or new API runtime is introduced.

**23:42 deployment diagnosis:** The owner created the Worker and started build
`998145af`. Cloning and dependency installation succeeded, but Cloudflare's
asdf-installed Python 3.12.15 lacked its `_sqlite3` extension. The exporter failed
on import before publishing. The original eight local checks did not reproduce
this provider-specific interpreter defect.

The Cloudflare requirements file now adds a pinned, self-contained SQLite wheel.
Only the Cloudflare entry point selects it, and only when `_sqlite3` is missing;
healthy Python installations retain the standard driver. The existing renderer,
read-only corpus queries and account/backend dependency file are reused unchanged.
Update the **build command** below before rebuilding the latest `main` revision.
The deploy command and four build variables stay as configured. The successful
Cloudflare retry and root-domain checks are now recorded below.

## Live hosting checkpoint — 11 October 2026, 00:12 BST

The owner supplied the successful build `eb4bc42f` for commit
`ce3463c547ac481304518137fc6458e1ee03c3e3`. The provider log confirms
the bundled SQLite driver worked, 1,908 useful public pages were exported and
the deploy completed in approximately seven minutes. Worker version:
`1f27c93d-0f6f-4c4d-8265-09a30083d889`.

The existing `scripts/verify_live_platform.py` was run against
`https://auction-geek.garethburke5.workers.dev` using the exact source snapshot
from that deployed commit. All 874 expected current listings and their checked
customer-visible facts matched, with no missing, unexpected or duplicate IDs.
This verifies publication fidelity, not source completeness: the reconciliation
still reported 40 degraded sources, which require separate existing launch review.

The owner then attached the root domain through the Worker's Domains tab.
Independent HTTP checks confirmed:
- `https://auctiongeek.co.uk/` returns 200 and the expected
  `/board/52c1e5f52013/index.json` link.
- The canonical URL is `https://auctiongeek.co.uk/`; the sitemap returns 200.
- The apex does not carry the preview host's `X-Robots-Tag: noindex`.
- Public configuration still has accounts and billing disabled.
- Plain HTTP currently returns 200 without redirecting to HTTPS.
- The `www` HTTPS probe failed at this environment's proxy; its DNS/redirect
  configuration has not passed acceptance. Local DNS resolution was unavailable
  for both apex and www, so it cannot independently establish missing DNS.

The confirmed apex custom domain is recorded in `wrangler.jsonc` for future
deployments. Still finish and verify HTTP-to-HTTPS and www redirects, mobile
browser acceptance and automatic propagation of collector pushes. A later
deployment of the updated configuration must also be checked.

## Verified position

The existing public static renderer supports a domain root without the old GitHub
project prefix. `web_platform.cloudflare` reuses it, emits Cloudflare headers,
keeps Workers/Pages preview hosts out of search indexes, and checks the free limits of
20,000 files and 25 MiB per asset before deployment. It requires an empty output
directory so stale files cannot be carried into the upload. Only that output
directory is published; the repository, databases and private reports are not.

Ten local tests passed: real renderer output at the custom-domain root,
canonical/sitemap/asset links, absence of private credential markers, default
account/payment gates, preview-host indexing rules, unsafe origin rejection,
stale output rejection and free-plan limit failures. Two fresh-interpreter cases
also export real fixture pages and historical records with normal SQLite and
with `_sqlite3` deliberately unavailable, using the real bundled driver. They
verify read-only query enforcement and that the compressed corpus is unchanged.
CI installs the same build dependency so this regression is exercised there.
These local checks establish packaging acceptance. Live hosting acceptance is
recorded below; neither constitutes investment-quality approval.

The GitHub-to-Cloudflare sign-in returned "Unable to sign in" twice, including
one fresh sign-in after the owner confirmed GitHub is the right method. No
Cloudflare project, DNS record, custom domain or certificate was created by that
remote sign-in attempt. The owner subsequently created the Worker in their own
browser; that does not provide this agent with a Cloudflare session. Stop retrying
the failed remote sign-in route.

## Cloudflare Workers Static Assets settings

Use the existing Cloudflare account and inspect Workers & Pages for an existing
project before creating anything. Reuse any existing Auction Geek project.
If none exists, use **Create application > Connect GitHub** to create one Worker connected only to
`garethburke5/Commercial-Auction-Sniper`. Select the Free plan. The owner completes
any GitHub integration authorisation; no API token or password belongs in chat.

| Setting | Value |
| --- | --- |
| Worker name | `auction-geek` (must match `wrangler.jsonc`) |
| Production branch | `main` |
| Root directory | Repository root |
| Build command | `python -m pip install -r web_platform/requirements-cloudflare.txt && python -m web_platform.cloudflare` |
| Deploy command | `npx wrangler@4 deploy` |
| Static asset output | `public-dist`, already declared in `wrangler.jsonc` |
| `PYTHON_VERSION` | `3.12` |
| `SKIP_DEPENDENCY_INSTALL` | `1` |
| `SITE_ORIGIN` | `https://auctiongeek.co.uk` |
| `BILLING_LIVE` | `false` |

Do not copy database, payment, AI or Supabase secret keys into the public build.
Leave account configuration unset until actual sign-in has passed acceptance.
Disable automatic preview-branch builds initially to conserve the free build
allowance. Normal `main` pushes, including published catalogue changes, must
trigger an updated site. Confirm that a collector/bot push also deploys, rather
than assuming the Git integration handles every trigger.

## Domain and acceptance sequence

1. Get the Worker build to succeed, then inspect its actual assigned `workers.dev`
   address. Check search, a property page, navigation, images, JSON indexes and
   the missing-page response before changing DNS. Run the existing
   `scripts/verify_live_platform.py` against that origin for source-to-live checks.
2. Inspect existing DNS first, preserving mail, verification and unrelated records.
   Add `auctiongeek.co.uk` through the Worker's **Settings > Domains & Routes >
   Add > Custom Domain** flow. Do not invent a CNAME target. Cloudflare must
   associate the domain with the Worker. Record the accepted custom-domain routes
   in `wrangler.jsonc` for future deployments. Wait for domain/certificate status
   to become active.
3. Add `www.auctiongeek.co.uk` and configure a permanent, path/query-preserving
   redirect to the apex using Cloudflare's domain redirect facility. Verify apex,
   www and HTTP-to-HTTPS behaviour. No paid plan is needed merely for this setup.
4. Verify canonical URLs, sitemap, robots, real property paths and source counts
   on the custom domain. Check the mobile view and browser console.
5. Coordinate the sign-in transition: Supabase Site URL becomes
   `https://auctiongeek.co.uk/`; allow the exact callback
   `https://auctiongeek.co.uk/account/`. Set the existing Render API's
   `PUBLIC_ORIGIN` to `https://auctiongeek.co.uk` for CORS and checkout return URLs.
   These settings are not changed before the custom domain works. Verify an
   actual owner's sign-in before public account activation.
6. Retire the old public GitHub Pages deployment or turn it into redirects only
   after the new site is verified. Do not redirect the working site to an
   unverified domain. GitHub Pages is not the intended paid commercial host.

Static asset requests and storage are free; Workers Builds has a separate free
allowance. Measure actual build minutes and scheduled update frequency during
acceptance. A script-free static Worker does not turn each page view into a
billable Python/API request. No paid plan has been selected.

Render continues to run the existing private Python API; Supabase continues to
hold its private account data. No scraper, analysis runtime, database or payment
implementation is duplicated. Report-quality and billing gates remain unchanged.

## Provider references checked

- https://pypi.org/project/pysqlite3-binary/0.5.4.post2/
- https://developers.cloudflare.com/workers/best-practices/workers-best-practices/
- https://developers.cloudflare.com/workers/ci-cd/builds/build-image/
- https://developers.cloudflare.com/workers/ci-cd/builds/limits-and-pricing/
- https://developers.cloudflare.com/workers/static-assets/headers/
- https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/
- https://developers.cloudflare.com/workers/platform/limits/
- https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

The public Worker and apex HTTPS host have passed the bounded checks above.
HTTP/www redirects, mobile interaction, bot-push propagation and the separate
account/payment/report-quality gates remain outstanding. Do not infer paid-launch
readiness from successful static hosting.

## HTTPS and WWW acceptance — 11 October 2026, 00:35 BST

The owner enabled Always Use HTTPS, added the proxied www A record using the
Cloudflare originless placeholder, and deployed the WWW redirect rule.
Independent HTTP checks now confirm:
- HTTPS apex returns 200.
- HTTP apex and both HTTP/HTTPS www return 301 to https://auctiongeek.co.uk/.
- A www properties URL retains its path and both query parameters exactly.
- Cloudflare build ee1028b9-d334-45b2-80fb-49fb4ba2d0ba for d7ff9580 completed
  successfully with the apex custom domain preserved in Wrangler.

These checks complete the hosting/redirect work above. Account, billing and
Acquisition Intelligence acceptance remain separate.
