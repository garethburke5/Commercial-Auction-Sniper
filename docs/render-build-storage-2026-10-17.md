# Render build storage recovery — 17 October 2026

## Failure and correction

Render deployment `dep-db9tmfgjgiss7392teig` failed after dependency installation. The platform event reports eviction because temporary `/tmp` storage exceeded 16 GB; it was not another application port-binding failure. The previous release continued serving.

Commit `a7d9b12aa1542c3957f5c39a4fde08e4ce12d317` adds `scripts/render_build.py`. In the disposable Render checkout only, it removes `.git` and raw `data/auction_history/sources`, then installs requirements without pip caching. The canonical compressed history database, history progress, property history and current catalogue remain. The script refuses other environments, unexpected roots, missing canonical runtime files and symlinked removal targets. It checks every target before deleting either directory.

The service build command was saved as `python scripts/render_build.py` and independently verified through the Render service API. The existing start command and `/healthz` check were retained. No source history was deleted from GitHub or the working repository; no customer data was removed.

## Verified deployment

The first automatic build had already captured the old command, so its success alone was not treated as acceptance. A subsequent clean-cache deployment, `dep-db9u15qog99s7390vim0`, ran the new script:

- 21:00:20 UTC: new build command and disposable Git removal logged.
- 21:00:23 UTC: raw source removal and canonical-data retention logged.
- 21:00:45 UTC: build succeeded.
- 21:01:38 UTC: deployment became live.

The next automatic release, `f73d32ba2e16e0d09c608afe2cc4814b56e224fa`, became live at 21:04:23 UTC (`dep-db9u3h6uverc738v150g`). This confirms an additional automatic update succeeded after the fix; it does not guarantee future platform availability.

## Verification and limits

Six build-safety tests passed. A disposable catalogue fixture returned the same 1,916 catalogue rows and three sampled history records before and after cleanup, while the original repository directories remained intact. The subsequent full collector suite passed 866 tests and 19 subtests.

Deployed HTTP checks at approximately 20:59 UTC returned:

| Check | Result |
| --- | --- |
| Readiness | 200; release `a7d9b12a`; accounts, owner configuration and sandbox billing configured |
| Account API without credentials | 401 |
| Owner tier preview without credentials | 401 |
| Stripe webhook without signature | 400 |
| Account preflight from `https://auctiongeek.co.uk` | 200; exact permitted origin |

The checked API responses used `Cache-Control: no-store`. Live billing, alert delivery and paid-report approval remained disabled. The analysis provider and production-email confirmation gates remained incomplete. These are access-control and deployment checks, not proof of the authenticated customer journey or production backup recovery.
