# Render deployment recovery — 17 October 2026

## Verified state

- Existing service: `auction-sniper-private-api` (`srv-db52g3jbc2fs73e380ag`), Frankfurt, Python 3, free instance.
- Manual recovery deployment `dep-db9q686q1p3s7396joo0` became live at 16:39 UTC with revision `8840c8b9a67052c723834b49f3edad6dd6fba38c`.
- Live HTTP health and readiness checks returned 200. Accounts and owner access reported configured.
- Live billing remains disabled; paid reports remain unapproved. Production email confirmation and analysis-provider configuration are still outstanding acceptance gates.

## Git provider repair

The Render repository selector initially showed no repositories despite Auto-Deploy being set to On Commit. With the owner's explicit approval, the Render GitHub app was installed with access limited to `garethburke5/Commercial-Auction-Sniper`. Render then displayed that repository.

The existing service was reconnected through Update Source on 17 October at approximately 16:56 UTC. Readback confirmed:
- Branch: `main`
- Build: `pip install -r web_platform/requirements.txt`
- Start: `uvicorn web_platform.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1`
- Health path: `/healthz`
- Automatic deployment: on commit
- No new service, instance upgrade, or billing activation.

## Acceptance still to verify

This checkpoint commit is also a real repository update for checking the repaired GitHub-to-Render delivery path. Confirm a Render deployment whose trigger is `new_commit`, then confirm its revision through `/api/readiness`. Do not count source settings alone as proof of automatic deployment.

Cheffins timed catalogue collection and its publication workflow passed after the collector/frontend test dependency split. Live public visibility must be checked separately. Cheffins rostrum coverage is not yet signed off.

This checkpoint does not close sandbox payment lifecycle, report quality/cost, email alerts, backup restoration, or the complete customer journey gates.
