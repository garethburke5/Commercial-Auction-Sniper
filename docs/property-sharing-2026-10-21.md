# Property sharing — 21 October 2026

The reusable `share.html` macro and `share.js` controller cover every rendered
property page, server-rendered and lazy-loaded search card, auctioneer/catalogue
card and Free Snapshot. Historical intelligence stays within the existing
property-page access controls. Shared URLs always target the public property
page, including when invoked from a snapshot; they contain no tracking query or
history fragment. No authentication, payment, AI or document processing is used.

Mobile coarse-pointer devices use Web Share when supported. Cancellation does
not reopen the menu; API denial/failure opens the fallback dialog. Desktop and
unsupported devices offer WhatsApp through `https://api.whatsapp.com/send?text=` (the recipient/group
is selected in WhatsApp), email, LinkedIn, Facebook, clipboard copy and a manually selectable
link if clipboard access fails. The native dialog provides keyboard focus
containment, Escape dismissal and return focus. No message is sent by the site.

Social metadata is rendered into the HTML, not added by JavaScript. Open Graph
and Twitter cards include the address, brand, structured public description,
guide, auction date, known availability status and the auctioneer's existing
property photograph. No unrelated/generated replacement image is inserted when
an image is missing. The static publisher makes a bounded best-effort pass to produce 1200×630 JPEGs
from existing photographs, with an Auction Geek band below the full contained
photo. Successful copies are hosted on Auction Geek; failed/blocked downloads
retain the original source image. No dimensions or file types are invented for
source-image fallbacks. Social-platform caches remain external factors. The image
pass has a 90-second budget, bounded downloads and private-address rejection.
Savills images use the same `resized/images/w1500` route seen in its own gallery,
avoiding full-size PNG originals that can exceed 30 MB.

Anonymous channel/action/placement counters use the existing Render operational
logging service. The public endpoint rejects extra dimensions and invalid
channel/action combinations, checks the site Origin and caps ingestion at 600
interactions per worker per minute. It receives no property URL, recipient,
account ID or cookie; browser DNT/GPC suppresses telemetry. Standard hosting
request logs remain subject to the host's own technical logging arrangements.
The owner-only `/api/admin/share-events` summary is explicitly limited to the
current API worker since its start; it is not a durable whole-site dashboard.
Retained `share_interaction` log records can be aggregated across that service's
log-retention period. Long-term traffic/SEO dashboards remain a separate existing
launch task. Counts are interactions, never delivered messages, unique people,
WhatsApp forwards or private-group activity. Ordinary page views/printing do not
emit share events, and telemetry failure does not block sharing.

Validation:
- Public metadata, prefix-aware canonical destinations, image absence, lazy card
  bundles and anonymous telemetry/access controls have automated regression tests.
- Existing Free Snapshot, Cloudflare, membership and history-access tests run.
- `sharing_browser.cjs` exercises 390px/1440px property, card and snapshot views,
  clipboard success/failure, clean channel URLs, keyboard/focus, native handoff,
  cancellation/failure and privacy signals. It sends no external messages.
- Actual WhatsApp/Facebook/LinkedIn rendered preview acceptance is distinct from
  fetching HTML with their crawler user agents. No private messaging delivery or
  device-native share-sheet rendering is claimed from mocked API tests.

Paid report and premium-history sales gates are unchanged. Continue the report
quality, historical collection/matching, billing and owner analytics roadmap.

Production verification, 21 October 2026 at 09:18 UTC:
- Release `71add957428ae47256b3544b014713d1cdf010bd` is live on Render;
  readiness returned 200, accounts ready, live billing disabled.
- Public workflow `39574788295` passed: 434 Python tests, 14 skips and three
  subtests, plus all six 390px/1440px sharing browser cases. Private PostgreSQL
  workflow `39574788499` passed.
- Main-domain Broadway page serves share asset `6868ad027e51`. Live Copy Link
  copied the exact canonical URL without query parameters. Hovered Copy Link
  uses white text on RGB(36,69,98), correcting the earlier contrast defect.
- The page's branded Open Graph image returned 200, image/jpeg, 146,129 bytes,
  1200×630, from `/static/share-images/864e66e731135e3c51dc6420.jpg`.
- Dedicated WhatsApp URL contains address, current guide, rent, auction date,
  Auction Geek attribution and canonical URL. Cloud-browser URL security blocked
  the app handoff. No message was sent. Actual Windows Chrome/Edge, Android/iOS
  app flows and received-message previews remain unverified; responsive Chromium
  and mocked native-share tests do not satisfy those device acceptance checks.
