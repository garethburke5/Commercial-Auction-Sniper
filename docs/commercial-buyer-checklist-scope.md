# Commercial Property Auction Buyer's Checklist — scoped backlog

Priority: after launch-critical billing, report-quality, alerts and recovery acceptance. Requested 17 October 2026. Assessment only; no new public page or homepage element has been deployed.

## Recommendation

One free, indexable educational page: **Commercial Property Auction Buyer's Checklist**, proposed URL `/commercial-auction-buyers-checklist/`. Reuse the existing site shell, glossary/educational layout, terminology, property links and Investment Reports journey. No new analysis engine, document uploader, authentication or checkout.

Discovery: a restrained footer/resource link and a contextual text link in the existing property-page Evidence and due diligence section. Link from relevant glossary/research content. Do not add another homepage strip or primary navigation row.

## Existing components inspected

- `web_platform/site.py`: route rendering, metadata, sitemap and existing glossary/methodology pages.
- `web_platform/templates/glossary.html` and educational styles in `static/site.css`: readable sections, section anchors and mobile layout.
- `templates/property.html`: existing Evidence and due diligence section, source/legal-pack links and property-context Investment Reports link.
- `templates/research.html` and `static/reviews.js`: existing report workflow and printable/downloadable report access. Keep these controls and ownership checks authoritative.
- `buyer_due_diligence.py`: legacy pack workspace now directs new analysis through the existing account-controlled report journey. Do not revive or duplicate the legacy uploader.
- Existing report evidence/limitations should be referenced, not recast as a checklist certification.

There is no general commercial buyer checklist in the inspected templates. Existing checkbox controls select documents or processing options; they are not buyer due-diligence progress tracking.

## Proportionate first release

Readable without JavaScript or registration. Around 30–40 concise prompts in these groups:

1. Property identity, tenure, title and access.
2. Commercial leases, passing income and income sustainability.
3. Tenant/guarantor covenant and arrears evidence.
4. EPC, energy obligations and jurisdiction-specific requirements.
5. Planning, lawful use and listed/conservation constraints.
6. Building condition, expenditure, services and environmental risks.
7. Special conditions, addenda and contractual obligations.
8. VAT, possible TOGC treatment and the applicable acquisition tax.
9. Acquisition costs, funding, stress tests and maximum bid.
10. Registration, bidding authority, deposits and auction-day checks.
11. Completion, insurance, handover and post-purchase obligations.

Prompts ask what evidence to obtain and which professional to involve. They do not calculate a valuation, decide tax treatment, interpret a lease as legal advice or assert compliance. Content must distinguish the applicable UK jurisdiction and be checked against current primary official sources before publication. Do not copy a competitor's wording or residential assumptions.

Small enhancement script: accessible task controls, section progress, reset with confirmation and an explicit optional “Remember progress on this device” control. Progress is task completion only, never a risk score, safety score or due-diligence pass. Clear text explains shared-device storage and how to clear it. The free reference content remains available if storage is blocked.

Print button uses a print stylesheet: expand all sections, retain source links and review date, include unchecked/resolved/remaining task labels, hide navigation and unnecessary controls. Reuse existing page styles rather than creating a separate PDF generation service.

## Keep task progress separate from evidence

Task states: Not started / In progress / Reviewed / Not applicable. A buyer selecting Reviewed means they reviewed that task; it is not a verified property finding.

If property context is introduced, show the property identity and link to its existing page and report request. Every property checklist begins with unverified matters. A public listing field must never automatically tick a legal, tax, compliance or title question.

Later, account-saved property checklists may reference dated, source-cited findings from an owned Investment Report, with unresolved matters and professional-review requirements shown separately. Only introduce this after report quality and account acceptance pass. Reuse existing property IDs and report ownership controls; do not copy private report content into public page markup or generic browser storage.

## Acceptance before publication

- Original commercial-investment content, current official sources, review date and jurisdiction handling.
- No claims that completion means a property is safe, compliant or ready to buy.
- No-script reading, keyboard controls, screen-reader labels, visible focus, reset and blocked-storage behaviour.
- Mobile widths 360/390/430, desktop and printed pages; no clipping or hidden unchecked tasks.
- Own canonical URL, sitemap entry, clear title/description and working contextual links. No change to existing report URLs or payment flows.
- No mandatory sign-up, paid report generation, email signup or intrusive promotion.

Defer cloud progress sync, document uploads, automatic verification and a checklist-specific PDF service. Those would widen scope and duplicate existing launch work.
