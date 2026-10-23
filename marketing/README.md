# Auction Geek social marketing

Status: **six drafts saved and independently read back from Buffer; automatic publishing is disabled**. A repeated live run retained the same six IDs and made no additional post writes. See `verification.json`. No paid AI, advertising, messaging API or new subscription is used. The existing GitHub Actions runner selects facts, calculates yields, renders JPEGs and calls Buffer. The public repository hosts the original images without a new service.

## Review and activation

- [Facebook drafts](https://publish.buffer.com/channels/6adb59c3778b240e2f9cee6d)
- [Instagram drafts](https://publish.buffer.com/channels/6adb7e1c778b240e2f9ee041)
- [Workflow and its review artifacts](https://github.com/garethburke5/Commercial-Auction-Sniper/actions/workflows/social-marketing.yml)
- `review/review.html`, `review/review.md` and `samples.json` contain the first six samples and their evidence. The source database is not modified.

Only after the owner approves the six samples and integration:

1. Set `publishing_approved` to `true` in `marketing/config.json`, recording the approval in `approval_note`.
2. Set repository Actions variable `SOCIAL_PUBLISHING_ENABLED` to `true`.
3. Run **Auction Geek social marketing → Run workflow → run**. Both switches are required. The default remains off. A push always runs the six-sample **draft** operation, regardless of approval.
4. Existing review drafts remain drafts. The automatic run selects fresh, not-previously-prepared properties. To publish an approved sample itself, recheck its date and evidence and schedule it in Buffer. Do not publish an expired sample.

The recurring workflow runs every six hours and after successful property collections. It uses Buffer's actual channel schedule and London timezone, up to three posts per calendar week per channel, including existing scheduled/sent manual posts when calculating capacity. It reserves the next available configured slot explicitly, so the auction-date check uses the actual intended publication time. It never uses `shareNow`. It queues no more than three posts per channel (below the Free plan's ten). Slots too close to execution or beyond seven days are skipped. Fewer posts are preferable to unsupported promotions.

## Pause immediately

**In Buffer, pause both channel queues.** This is the fastest way to prevent already queued posts from publishing and also works if GitHub or the API key is unavailable.

Then run **Auction Geek social marketing → Run workflow → pause**. This sets the durable pause flag and moves this agent's scheduled posts back to drafts; it leaves unrelated manual posts alone. Setting Actions variable `SOCIAL_PUBLISHING_ENABLED=false` prevents new scheduled writes. To resume after owner authorisation, clear `paused` in `marketing/state.json` and `config.json`, restore the variable, and unpause the Buffer queues. Disabling the GitHub workflow alone does **not** cancel posts already in Buffer.

## Evidence and editorial rules

- Current commercial/mixed-use lots only, with a healthy collector, dated evidence no older than 14 hours, and auctions at least three days after publication.
- Exclude sold, withdrawn, postponed, stale, undated and unknown-status opportunities. No assumption that a retained public history page is still available to buy.
- Rent must be current, supported by matching source wording or a reconciled tenancy schedule. Historic/potential rent and conflicting totals are excluded. Multi-let/HMO income needs a reconciled schedule. Yields over 20% go to editorial review, not automatic promotion.
- Recalculate gross yield; for a guide range use the upper end and label it. Purchase and running costs are explicitly excluded. No guarantees, valuations or investment recommendations.
- Use short, complete letting statements for tenant names; never infer credit strength from a tenant's name or describe neighbouring occupiers as tenants.
- Previous appearances are linked through the existing reusable property relationship engine. Price comparison additionally requires identical recorded titles, unit count, floor area, tenure and rent. Different legal interests are never advertised as discounts. Guides remain guides, not sale prices.
- Raw interface text, overlong addresses and captions are rejected. Each caption and image has an evidence record and fingerprint.
- Agent-owned queued property posts return to drafts if evidence becomes stale, a lot disappears/withdraws, or an advertised fact changes. This uses the latest existing collector data; it is not a real-time guarantee against changes made after a source check.
- Occasional original educational posts use explicitly hypothetical examples and no fresh AI calls. Topics rotate, with a minimum 90-day gap before reuse. The initial set includes one educational post per channel.

## Images

Initial samples use original navy/teal typographic cards, 1080 × 1080, with no stock or generated property imagery. No documented social reuse permission was found for the collected auctioneer photographs. `photo_permissions.json` accepts **exact image URL**, `social_reuse: true`, `permission_evidence`, `expires_on` and `attribution`; only then can the renderer fetch a genuine photograph. A public photograph or existing webpage preview is not assumed to grant advertising rights. Prime photographs remain withheld. Photo failures fall back to original cards.

## Buffer Free limits and permissions

Verified 23 October 2026: both configured channels connected, unlocked; manage/schedule post permissions present. Instagram: Monday 08:30, Wednesday 09:37, Friday 08:30. Facebook: Wednesday 09:41, Thursday 09:39, Friday 08:58. All Europe/London, including DST. These times are read live, not hard-coded.

Official Free limits: up to 3 channels, 10 scheduled posts per channel, 3,000 requests per rolling 30 days. Developer documentation lists 100 requests/15 minutes and 250/24 hours; Buffer's API landing page currently says 100/24 hours. The runner conservatively caps itself at 35 requests per run and follows response rate-limit headers and 429 Retry-After. It defers rather than requesting an upgrade. Extra manual runs and other API users share the allowance.

Read-only operations can retry bounded transient failures. Mutations are never automatically replayed after a timeout. A durable intent is written to GitHub **before** each mutation. On rerun, the agent reconciles Buffer posts by channel and caption hash. An unresolved intent remains blocked for manual review. Successful, rejected and unknown attempts are journalled in `state.json`; run failures and available metrics appear in the Actions artifact. Workflow concurrency prevents two agents scheduling concurrently.

## Key expiry and renewal

Current key expiry: **22 November 2026**. The scheduled job writes an Actions warning from **1 November** (21 days before expiry), with days remaining and the renewal instructions. It refuses API work on the expiry date. Warnings appear in run summaries/logs; no email or Slack service is configured.

1. Open Buffer → Settings → API / Developer settings (https://publish.buffer.com/settings/api).
2. Generate/rotate the personal API key for the same organisation, retaining `account:read`, `posts:read`, `posts:write` and including `insights:read` for engagement reporting. The Free plan permits one key; follow Buffer's replacement flow.
3. Paste it directly into GitHub repository → Settings → Secrets and variables → Actions → `BUFFER_API_KEY` → Update. Never paste it into a report, code, issue or chat.
4. Update `key_expires_on` in `marketing/config.json` to the new expiry shown by Buffer.
5. Run **Social marketing connection check**, then the main workflow in `monitor` mode. Keep publishing paused until the check succeeds.

Credentials are passed only through Actions environment variables. Buffer authentication requests refuse redirects; credentials and arbitrary remote error bodies are not logged. GitHub tokens only write under `marketing/`. No secrets are stored in the review manifest, ledger or images.

## Traffic and performance

Facebook links point to the canonical Auction Geek property URL with `utm_source=facebook`, `utm_medium=organic_social`, campaign and property ID. Ordinary copied property links remain unchanged. Instagram captions direct visitors to the profile website link and give a property search term. Recommended profile website: `https://auctiongeek.co.uk/?utm_source=instagram&utm_medium=organic_social&utm_campaign=profile`. This implementation does not silently change the Instagram profile.

The runner attempts to collect available Buffer post metrics, preserving the metric name, unit and last-updated date. Missing metrics are reported as unavailable, never zero. Metrics are for the latest 30 sent posts, with a pagination flag if more exist. The agent has published no posts during setup. An existing manually published account post is left untouched. The metrics call currently returns `INSUFFICIENT_SCOPE`: the key grants `account:read`, `posts:read`, `posts:write`, `ideas:read`, but lacks `insights:read`. Add `insights:read` in Buffer API key settings if editable, or include it when replacing the key. The settings page requires sign-in in this session, so this permission was not changed. This is reported as unavailable and must not be presented as zero engagement.

UTM links enable attribution in a compatible site analytics system. This integration does not establish that Cloudflare Web Analytics/GA has been activated or that its credentials are available. Until verified, report Buffer engagement separately from actual website visits. Likes or reach are not visits; Instagram caption links are not clickable, and private forwards cannot be measured reliably.

## Local verification

`python -m pytest marketing/tests -q`

Dependencies: Python 3.11+, Pillow, requests, beautifulsoup4, pytest and DejaVu Sans (included on Ubuntu Actions runners). The unit/integration tests use fake clients and do not call Buffer or publish. Live write verification uses `saveToDraft:true` and checks the returned and subsequently fetched status.

## Official API references

- https://developers.buffer.com/examples/create-draft-post.html
- https://developers.buffer.com/guides/posts-and-scheduling.html
- https://developers.buffer.com/guides/api-limits.html
- https://developers.buffer.com/reference.html
- https://buffer.com/pricing
