# Property sharing — 21 October 2026

The reusable `share.html` macro and `share.js` controller cover every rendered
property page, server-rendered and lazy-loaded search card, auctioneer/catalogue
card and Free Snapshot. Historical intelligence stays within the existing
property-page access controls. Shared URLs always target the public property
page, including when invoked from a snapshot; they contain no tracking query or
history fragment. No authentication, payment, AI or document processing is used.

Mobile coarse-pointer devices use Web Share when supported. Cancellation does
not reopen the menu; API denial/failure opens the fallback dialog. Desktop and
unsupported devices offer WhatsApp (the recipient/group is selected in
WhatsApp), email, LinkedIn, Facebook, clipboard copy and a manually selectable
link if clipboard access fails. The native dialog provides keyboard focus
containment, Escape dismissal and return focus. No message is sent by the site.

Social metadata is rendered into the HTML, not added by JavaScript. Open Graph
and Twitter cards include the address, brand, structured public description,
guide, auction date, known availability status and the auctioneer's existing
property photograph. No unrelated/generated replacement image is inserted when
an image is missing. Images remain hosted on the existing source services;
their uptime and each social platform's preview cache remain external factors.
No dimensions or file types are invented for source images.

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
