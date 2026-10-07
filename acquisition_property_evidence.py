"""Narrow, source-bound property outcomes for acquisition reports.

These rules read conclusions and replies, not the presence of a topic in a
question, legend or lease covenant. Dated findings are not silently promoted
to present condition. Table values without reliable row relationships remain
explicit review tasks. All evidence retains its document hash and PDF page.
"""
from __future__ import annotations

import hashlib
import re


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _pages(document):
    return document.metadata.get("pages") or [{"page": None, "text": document.text, "ocr": False}]


def _match(document, pattern, *, pages=None):
    for page in pages if pages is not None else _pages(document):
        text = _norm(page.get("text"))
        match = re.search(pattern, text, re.I)
        if match:
            return page, text, match
    return None


def _evidence(document, hit, context=100):
    page, text, match = hit
    start = max(0, match.start() - context)
    end = min(len(text), match.end() + context)
    if start:
        start = text.find(" ", start) + 1
    if end < len(text):
        end = text.rfind(" ", start, end)
    return {"document": document.name, "page": page.get("page"),
            "excerpt": text[start:end], "ocr": bool(page.get("ocr")),
            "document_sha256": document.sha256}


def extract_property_evidence(documents):
    """Return consolidated acquisition finding dictionaries from PackDocuments.

    No external lookups or current-time assumptions are made. An old report may
    have been superseded outside the pack; action completion is never inferred.
    """
    documents = list(documents)
    findings = []
    asbestos = [d for d in documents if re.search(r"asbestos inspection\b", _norm(d.text[:1800]), re.I)]

    def add(key, document, hits, title, found, why, meaning, next_step,
            section="concerns", severity="NEEDS CHECKING", visual=False):
        evidence = [_evidence(d, hit) for d, hit in hits if hit]
        if not evidence:
            return
        findings.append({
            "id": key + "-" + hashlib.sha256(document.name.encode()).hexdigest()[:8],
            "title": title, "found": found, "why": why, "meaning": meaning,
            "next_step": next_step, "evidence": evidence, "section": section,
            "severity": severity, "requires_visual_review": visual,
        })

    for d in documents:
        first = _norm(d.text[:2200])
        name = d.name.lower()
        # A policy certificate result is not a lease promise to insure.
        if re.search(r"policy certificate|schedule of insurance", first, re.I):
            hit = _match(d, r"\bSubsidence(?: extension)?\s*:?\s*(Not Included|Not insured|Excluded)\b")
            if hit:
                dates = _match(d, r"Date this cover starts:\s*[\d/.-]+.{0,80}?Date this cover expires:\s*[\d/.-]+")
                add("insurance-subsidence", d, [(d, hit), (d, dates)],
                    "Subsidence excluded from the supplied cover",
                    "The supplied insurance certificate explicitly excludes subsidence cover.",
                    "Uninsured ground movement can leave the owner with repair costs and affect lender acceptance.",
                    "The certificate is evidence of the stated policy period, not a binding quote for the purchaser.",
                    "Obtain a binding purchaser insurance quotation and lender acceptance, including the subsidence exclusion and flood terms.",
                    section="property")

        environmental = "groundsure" in name or ("professional opinion" in first.lower() and "contaminated" in first.lower())
        if environmental:
            hit = _match(d, r"A high risk of groundwater flooding has been identified at a building/structure level.{0,230}?damage\.")
            if hit:
                add("groundwater", d, [(d, hit)], "High modelled groundwater flood risk",
                    "The environmental search identifies high groundwater flood risk at building level, including potential basement and ground-floor effects.",
                    "Basement use, repairs, interruption of rent and insurance terms can be affected.",
                    "This is a modelled hazard, not confirmation that flooding has occurred.",
                    "Ask for flooding history and inspect the basement; confirm groundwater/flood and loss-of-rent cover and price any resilience works.", section="property")
            hit = _match(d, r"The property, or an area within \d+m of the property, has a (moderate to high|high) potential for natural ground subsidence\.")
            if hit:
                add("ground-stability", d, [(d, hit)], "Modelled ground instability needs survey review",
                    "The search identifies " + hit[2].group(1).lower() + " potential for natural ground subsidence at or near the property.",
                    "Ground movement can affect repair costs, insurability and finance.",
                    "The geological model is not evidence of actual subsidence or a historic claim.",
                    "Have the surveyor assess movement and foundation risk and reconcile the conclusion with available insurance cover.", section="property")
            hit = _match(d, r"Groundsure considers there to be an acceptable level of risk at the site from contaminated land liabilities\.")
            if hit:
                add("contamination", d, [(d, hit)], "Contaminated-land screening conclusion",
                    "The search concludes an acceptable level of contaminated-land liability risk.",
                    "This separates the search's favourable contamination result from its other environmental hazards.",
                    "It is a desk-based conclusion for the search date and site extent, not a physical condition warranty.",
                    "Confirm that the searched boundary covers the acquisition and review any later use or incident.", section="property", severity="INFORMATION")

        # An actual FRA report has an assessment date and summary, unlike CPSE questions.
        if re.search(r"fire.{0,100}?risk assessment", first, re.I) and re.search(r"date of assessment", first, re.I):
            date_hit = _match(d, r"Date of assessment:\s*(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})")
            review = _match(d, r"Recommended review date:\s*([A-Za-z]+\s+\d{4})")
            risk = _match(d, r"overall risk of harm is deemed to be:\s*FIRE SAFETY\s*(LOW|MEDIUM|HIGH)\b")
            count = _match(d, r"Total number of actions identified:\s*(\d+)\b")
            scope = _match(d, r"Areas inspected:.{5,200}?Areas excluded:.{5,300}?(?:2nd floor[^.]*\)|\.)")
            action_patterns = [
                (r"Upgrade automatic fire detection and warning system in the common areas", "alarm upgrading"),
                (r"Undertake remedial works to.{0,90}?penetrations in the locations.{0,90}?identified", "fire stopping"),
                (r"Verify whether fixed wiring.{0,12}?certificate is available and up to date", "electrical certification"),
                (r"develop simple, written emergency evacuation plan", "evacuation planning"),
                (r"ensure that the emergency lighting is tested", "emergency-lighting tests"),
                (r"Install or replace intumescent strips.{0,45}?and/or smoke seals", "fire-door seals"),
            ]
            actions = [(hit, label) for pattern, label in action_patterns if (hit := _match(d, pattern))]
            if date_hit and (risk or count or actions):
                found = "The " + date_hit[2].group(1) + " assessment"
                found += " rates fire risk " + risk[2].group(1).lower() if risk else " contains an action plan"
                if count:
                    found += " and records " + count[2].group(1) + " actions"
                found += "."
                if review:
                    found += " Its recommended review date is " + review[2].group(1) + "."
                if actions:
                    found += " Recommendations include " + ", ".join(label for _, label in actions) + "."
                add("fire-actions", d, [(d, h) for h in [date_hit, review, risk, count, scope] if h] + [(d, h) for h, _ in actions],
                    "Dated fire action plan requires closure evidence", found,
                    "Unresolved safety works can create immediate management obligations and unbudgeted expenditure.",
                    "These were findings at the assessment date. Neither current defects nor completion of the actions is established by this report alone; excluded demises need separate review.",
                    "Obtain the latest fire assessment, evidence closing each action, current testing records and tenant assessments; cost any work still required.", section="property")

        if re.search(r"\bCPSE[. ]?7\b", first, re.I) or re.search(r"cpse[ .]?7", name):
            hit = _match(d, r"4\.4\s+Please supply copies of the most recent asbestos survey and asbestos management plan.{0,120}?None available\.")
            if hit:
                other_hits = [(doc, _match(doc, r"Asbestos Inspection.{0,60}?Report")) for doc in asbestos]
                add("cpse-asbestos", d, [(d, hit)] + other_hits,
                    "Asbestos enquiry reply needs reconciliation" if asbestos else "No asbestos records supplied in the enquiry reply",
                    "The CPSE reply says no asbestos survey or management plan is available." + (" Separate asbestos inspection reports are included in the supplied pack." if asbestos else ""),
                    "Contradictory or incomplete records prevent a reliable view of present asbestos management.",
                    "The reply does not establish an asbestos-free property, nor does an older report establish current management compliance.",
                    "Ask the seller to reconcile the reply with the surveys and supply the current register, management plan, reinspection and any removal records.", section="cpse")
            hit = _match(d, r"EPC for the commercial premises to\s+follow\.")
            follow = None
            if not hit:
                # This reply can span two PDF pages. Require the continuation at
                # the start of the immediately following page, not any later mention.
                pages = _pages(d)
                for i, page in enumerate(pages[:-1]):
                    candidate = _match(d, r"EPC for the commercial premises to\b", pages=[page])
                    continuation = _match(d, r"^follow\.", pages=[pages[i + 1]])
                    if candidate and continuation:
                        hit, follow = candidate, continuation
                        break
            if hit:
                add("cpse-commercial-epc", d, [(d, hit), (d, follow)], "Commercial EPC promised in the replies",
                    "The seller's CPSE reply says the commercial EPC is to follow.",
                    "Rating, extent and any relevant letting implications cannot be established from that promise.",
                    "This records an incomplete reply; it does not establish the energy rating or an exemption.",
                    "Obtain the actual current commercial certificate for each demise, or supporting exemption evidence, before relying on letting compliance.", section="cpse")

        if re.search(r"\bCPSE[. ]?2\b", first, re.I) or re.search(r"cpse[ .]?2", name):
            hit = _match(d, r"No current outstanding rent arrears\.\s*Buyer to rely on documentation provided\.")
            if hit:
                add("cpse-rent-arrears", d, [(d, hit)], "Seller states no current rent arrears",
                    "The CPSE reply states no current outstanding rent arrears, with reliance on the documents supplied.",
                    "A payment ledger supports collection history but does not by itself prove the contractual annual income.",
                    "This is the seller's dated statement about rent; it does not clear separate works or service-charge balances.",
                    "Obtain an updated tenant-by-tenant rent, service-charge and other-debt reconciliation at completion.", section="income", severity="INFORMATION")

        # Water search responses using the wrong apparent property category are
        # incomplete connection evidence, even when the headline says 'See details'.
        if re.search(r"Drainage\s*&\s*Water (?:Enquiry|Search)", first, re.I):
            foul = _match(d, r"2\.1\s+Does foul water from the property drain to a public sewer\?\s+The enquiry appears to relate to a plot of land or a recently built property\.")
            water = _match(d, r"3\.1\s+Is the property connected to mains water supply\?\s+The enquiry appears to relate to a plot of land or a recently built property\.")
            if foul or water:
                add("water-search-scope", d, [(d, foul), (d, water)], "Water-search connections remain unconfirmed",
                    "The water search answers connection enquiries by referring to a plot of land or recently built property, rather than confirming the actual connections.",
                    "Supply, drainage routes and associated rights or costs remain unverified.",
                    "Check the search address and boundary; this response is not proof either of connection or of missing services.",
                    "Obtain a corrected or clarified search and current utility accounts; confirm physical connections and relevant service rights.", section="property")

        if d in asbestos:
            negative = _match(d, r"No suspect materials were detected within the remit of this survey\.")
            if negative:
                add("asbestos-scope-negative", d, [(d, negative)], "Negative asbestos finding has a limited scope",
                    "This asbestos report found no suspect materials within the remit of its survey.",
                    "The result applies to the surveyed area and date; it does not cover every demise, concealed space or later alteration.",
                    "A negative result in one survey must not overwrite a positive finding in another survey.",
                    "Reconcile the survey date and inspected areas with today's layout, and obtain current management or refurbishment evidence where needed.", section="property", severity="INFORMATION")
            # A labelled sample result is stronger than a glossary or risk legend.
            positive = _match(d, r"Asbestos Type\.\s*((?:Trace\s+)?(?:Crocidolite|Chrysotile|Amosite)(?:\s*/\s*(?:Low\s+)?(?:Chrysotile|Crocidolite|Amosite))?)\b")
            if positive:
                sample = _match(d, r"Sample No[.,]?\s+[A-Z0-9]+", pages=[positive[0]])
                add("asbestos-sample", d, [(d, positive), (d, sample)], "Asbestos identified in a dated sample",
                    "A sample entry in the supplied asbestos survey identifies " + positive[2].group(1) + ".",
                    "Existing or disturbed asbestos may require management, specialist works and a cost allowance.",
                    "The dated sample is not proof of the material's present condition or current demise. Risk legends elsewhere in the report are not findings for this sample.",
                    "Verify the sample location and rating visually, map it to today's layout and obtain current reinspection or removal evidence before pricing work.", section="property", visual=True)

        # Do not attach a detached OCR numeric column to a reserve label. Report
        # the unresolved table and request visual reconciliation, never a new cost.
        if re.search(r"service charge collected", d.text, re.I) and re.search(r"rese?rve?s? fund", d.text, re.I):
            hit = _match(d, r"(?<![\d/])-[£ ]?\d+\.\d{2}\b")
            if hit:
                add("service-charge-table", d, [(d, hit)], "Service-charge accounts need reconciliation",
                    "The supplied service-charge accounts contain a negative amount in a table with reserve-fund balances.",
                    "A reserve shortfall or incorrect accounting period can affect cash funding and completion apportionments.",
                    "The table requires visual reconciliation; this is not an established buyer liability or a deduction from net income.",
                    "Obtain corrected current accounts, the reserve reconciliation, recoverability by demise and confirmation of funds transferred on completion.", section="income", visual=True)
    return findings
