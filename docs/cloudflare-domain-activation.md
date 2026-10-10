# Auction Geek domain activation

Prepared 10 October 2026. The owner authorised connecting `auctiongeek.co.uk`,
purchased through Cloudflare. This is a hosting/domain task, not paid-launch approval.

## Verified position

The existing public static renderer supports a domain root without the old GitHub
project prefix. `web_platform.cloudflare` reuses it, emits Cloudflare headers,
keeps preview hosts out of search indexes, and checks the free Pages limits of
20,000 files and 25 MiB per asset before deployment. It requires an empty output
directory so stale files cannot be carried into the upload. Only that output
directory is published; the repository, databases and private reports are not.

Eight local tests passed: real renderer output at the custom-domain root,
canonical/sitemap/asset links, absence of private credential markers, default
account/payment gates, preview-host indexing rules, unsafe origin rejection,
stale output rejection and free-plan limit failures. This is packaging acceptance,
not a live Cloudflare deployment or a new investment-quality approval.

The GitHub-to-Cloudflare sign-in returned "Unable to sign in" twice, including
one fresh sign-in after the owner confirmed GitHub is the right method. No
Cloudflare project, DNS record, custom domain or certificate has been created or
changed by this work. Stop retrying that browser sign-in route.

## Cloudflare Pages settings

Use the existing Cloudflare account and inspect Workers & Pages for an existing
project before creating anything. Reuse any existing Auction Geek project.
If none exists, create one Pages project connected only to
`garethburke5/Commercial-Auction-Sniper`. Select the Free plan. The owner completes
any GitHub integration authorisation; no API token or password belongs in chat.

| Setting | Value |
| --- | --- |
| Project name, if a new project is needed | `auction-geek` (subject to availability) |
| Production branch | `main` |
| Framework | None |
| Root directory | Repository root |
| Build command | `python -m pip install -r web_platform/requirements.txt && python -m web_platform.cloudflare` |
| Build output directory | `public-dist` |
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

1. Get the Pages build to succeed, then inspect its actual assigned `pages.dev`
   address. Check search, a property page, navigation, images, JSON indexes and
   the missing-page response before changing DNS. Run the existing
   `scripts/verify_live_platform.py` against that origin for source-to-live checks.
2. Inspect existing DNS first, preserving mail, verification and unrelated records.
   Add `auctiongeek.co.uk` through the Pages project's **Custom domains** flow.
   Do not merely invent a CNAME target. Cloudflare must associate the domain
   with the project. Wait for domain/certificate status to become active.
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

Render continues to run the existing private Python API; Supabase continues to
hold its private account data. No scraper, analysis runtime, database or payment
implementation is duplicated. Report-quality and billing gates remain unchanged.

## Provider references checked

- https://developers.cloudflare.com/pages/framework-guides/deploy-anything/
- https://developers.cloudflare.com/pages/configuration/build-image/
- https://developers.cloudflare.com/pages/configuration/headers/
- https://developers.cloudflare.com/pages/configuration/custom-domains/
- https://developers.cloudflare.com/pages/platform/limits/
- https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits

Provider deployment, DNS, HTTPS, build duration and bot-push propagation still
need live acceptance. Local tests or a repository commit are not evidence that
Cloudflare hosting is active.
