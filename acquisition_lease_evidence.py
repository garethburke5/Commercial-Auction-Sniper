"""Narrow, document-scoped lease facts for acquisition reports.

Each letting stays separate. Extracted initial rent is not certified passing rent;
draft dates and scanned amendments remain source wording for a conveyancer to check.
"""
from __future__ import annotations

import hashlib
import re

from legal_pack_review import document_pages, norm

MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"


def _pages(document):
    for page in document_pages(document):
        text = norm(page.get("text", ""))
        if re.search(r"\.{5,}", text) and re.search(r"\bcontents\b", text[:250], re.I):
            continue
        if text:
            yield page, text


def _evidence(document, page, text):
    return {"document": document.name, "page": page.get("page"),
            "excerpt": norm(text), "ocr": bool(page.get("ocr")),
            "document_sha256": document.sha256}


def _matches(document, pattern, limit=3):
    result = []
    for page, text in _pages(document):
        for match in re.finditer(pattern, text, re.I):
            result.append((match, _evidence(document, page, match.group(0))))
            if len(result) >= limit:
                return result
    return result


def _uncertain_date(text):
    """Two adjacent month names expose common PDF overlay/OCR amendment errors."""
    return bool(re.search(MONTH + r"\s*" + MONTH, text, re.I)
                or re.search(r"\[\s*\]", text)
                or re.search(r"\b(?:tbc|to be confirmed|insert date)\b", text, re.I))


def extract_lease_evidence(documents):
    leases, findings = [], []

    def finding(document, suffix, title, found, why, meaning, action, evidence,
                severity="NEEDS CHECKING", impact=None):
        findings.append({
            "id": "lease-" + hashlib.sha256((document.name + suffix).encode()).hexdigest()[:12],
            "title": title, "found": found, "why": why, "meaning": meaning,
            "next_step": action, "evidence": evidence, "section": "lease",
            "severity": severity, "impact": impact,
        })

    for document in documents:
        if getattr(document.doc_type, "value", document.doc_type) != "lease":
            continue
        pages = list(_pages(document))
        text = " ".join(value for _, value in pages)
        if not re.search(r"\b(?:lease|tenant|rent)\b", text, re.I):
            continue
        row = {"document": document.name, "evidence": [], "tenant": None,
               "annual_rent": None, "rent_basis": "Lease amount; current collection not certified",
               "term": None, "breaks": [], "reviews": [], "repairs": [], "service_charge": [],
               "security": None, "guarantee": "No separately identified guarantor established",
               "rent_deposit": "No existing deposit established from the lease text"}

        parties = _matches(document,
            r"\(2\)\s*([A-Z][A-Z ,.&'’()\-]{2,140}?)\s+of\s+.{3,180}?\(Tenant\)", 1)
        if not parties:
            parties = _matches(document,
                r"\bTenant\s+([A-Z][A-Z ,.&'’()\-]{2,140}?)\s+of\s+.{3,180}?(?=\bLR4\b|\bBackground\b)", 1)
        if parties:
            match, ev = parties[0]
            row["tenant"] = norm(match.group(1))
            row["evidence"].append(ev)

        rents = _matches(document,
            r"\b(?:Annual|Initial|Yearly) Rent[’'\"]?\s*(?::|means)?\s*(?:rent\s+)?(?:at\s+)?(?:a\s+)?(?:rate\s+of\s+|the yearly sum of\s+)?[^£.]{0,80}£\s*([\d,]+(?:\.\d{1,2})?)", 3)
        amounts = {float(m.group(1).replace(",", "")) for m, _ in rents}
        if len(amounts) == 1:
            row["annual_rent"] = next(iter(amounts))
            row["evidence"].append(rents[0][1])
        elif len(amounts) > 1:
            finding(document, "rent-conflict", "Different lease rent amounts need reconciliation",
                    "; ".join(ev["excerpt"] for _, ev in rents),
                    "An initial or revised rent cannot safely be selected from competing amounts.",
                    "No single annual rent has been assigned to this lease.",
                    "Confirm the operative rent, period, any variation and payment ledger.",
                    [ev for _, ev in rents])

        terms = _matches(document,
            r"\b(?:Contractual Term:\s*)?(?:a\s+)?term (?:of\s+)?(?:\d+|FIVE|TEN|FIFTEEN|TWENTY)[ -]?years from.{0,150}?(?:\]\s*20\d{2}|\b20\d{2}\b)(?:\.)?", 1)
        if terms:
            row["term"] = {"text": terms[0][0].group(0),
                           "uncertain": _uncertain_date(terms[0][0].group(0)),
                           "evidence": [terms[0][1]]}
            row["evidence"].append(terms[0][1])

        # A defined break date plus the operative tenant/landlord termination power.
        # A contents heading, generic forfeiture or guarantor new-lease clause is not a break.
        for page, value in pages:
            date = re.search(r"[‘'’\"]?Break Date[’'‘\"]?\s*:?\s*(\[[^\]]{1,100}\]\s*20\d{2}|\d{1,2}\s+" + MONTH + r"\s+20\d{2})", value, re.I)
            power = re.search(r"\b(The\s+)?(Tenant|Landlord|Either party) may (?:terminate|determine) (?:this |the )?[Ll]ease.{0,260}", value, re.I)
            if not (date and power):
                continue
            start = max(0, date.start() - 100)
            end = min(len(value), power.end() + 1350)
            excerpt = value[start:end]
            notice = re.search(r"not less than\s+(?:\w+|\d+)\s+(?:months?|weeks?|days?)[^.;]{0,100}", excerpt, re.I)
            condition = re.search(r"(?:Break Notice shall have no effect|Subject to clause\s+[\d.]+)[\s\S]{0,1000}", excerpt, re.I)
            ev = _evidence(document, page, excerpt)
            item = {"party": power.group(2), "date_raw": norm(date.group(1)),
                    "notice_raw": norm(notice.group(0)) if notice else None,
                    "conditions_raw": norm(condition.group(0)) if condition else None,
                    "uncertain": _uncertain_date(date.group(1)), "evidence": [ev]}
            row["breaks"].append(item)
            finding(document, "break-" + str(page.get("page")),
                    "Tenant break limits income certainty" if power.group(2).lower() == "tenant" else "Lease break requires review",
                    f"{power.group(2)} break date wording: {item['date_raw']}. " + (item["notice_raw"] or "Notice period not established from this extract."),
                    "The contractual expiry is not the earliest date on which rent may stop.",
                    "Assess letting risk and cash flow at the break; the right remains conditional on the full clause.",
                    "Confirm the effective date, notice deadline, satisfaction of all break conditions and any notice already served.", [ev])

        review_dates = _matches(document,
            r"[‘'’\"]?(?:The )?Review Dates?[’'‘\"]?\s*(?::|means)\s*.{0,180}?(?:\b20\d{2}\b[^.]{0,75}\.|Commencement Date\.|anniversary[^.]{0,100}\.)", 2)
        for match, ev in review_dates:
            row["reviews"].append({"text": match.group(0), "evidence": [ev]})
        if re.search(r"\bCPI\b|Consumer Prices Index", text, re.I):
            row["review_method"] = "CPI wording identified; verify the operative formula and cap/collar"
        elif re.search(r"Open Market Rent", text, re.I):
            row["review_method"] = "Open-market rent wording identified; verify the operative floor and assumptions"

        # Long residential leases are ground-rent evidence, not additional occupational lettings.
        long_term = bool(re.search(r"\b(?:99|125|199|250|999)\s+years\b", text, re.I))
        residential = bool(re.search(r"\b(?:The Flat|First Floor Flat|Second Floor Flat|residential flat)\b", text, re.I))
        row["interest"] = "Residential long lease" if long_term and residential else "Occupational lease / confirm interest"
        if long_term and residential and rents:
            row["ground_rent"] = {"initial_amount": row["annual_rent"],
                                  "current_amount": None,
                                  "basis": "Initial ground rent only; apply review dates and confirm demands/receipts",
                                  "evidence": [ev for _, ev in rents]}
            doubles = _matches(document,
                r"(?:For (?:the|each) succeeding period of \d+ years).{0,230}?(?:twice the Initial Rent|twice the amount[^.]{0,150})\.", 2)
            if doubles:
                row["ground_rent"]["review_wording"] = " ".join(m.group(0) for m, _ in doubles)
                row["ground_rent"]["evidence"].extend(ev for _, ev in doubles)
                finding(document, "ground-review", "Ground rent has a future review mechanism",
                        row["ground_rent"]["review_wording"],
                        "The stated initial rent is not necessarily the rent for every year of the long lease.",
                        "Treat residential income as ground rent and a long-term reversion, not vacant-possession flat income.",
                        "Confirm the next review date, applicable provisos, current demands and collections.",
                        [ev for _, ev in doubles] + [ev for _, ev in review_dates], "INFORMATION")

        for pattern in [
            r"(?:Tenant must|Tenant shall).{0,80}keep (?:the Property|the Flat).{0,180}?repair[^.]{0,180}\.",
            r"Tenant shall pay.{0,160}proportion.{0,180}external and structural repairs[^.]{0,150}\.",
            r"Landlord shall use reasonable endeavours.{0,320}reasonable state of repair\.",
            r"Service Charge:\s*a fair proportion.{0,600}?(?:Service Charge\.|Services\.)",
            r"(?:To\s+repair.{0,30}exterior and structure of the Building\s+)?The Landlord must:\s*(?:\d+\.[\d.]+\s*)?repair and where necessary renew the foundations.{0,130}?Building[;.]",
        ]:
            for match, ev in _matches(document, pattern, 1):
                row["repairs"].append({"text": match.group(0), "evidence": [ev]})
        if row["repairs"]:
            row["repair_basis"] = "Read with demised extent, retained structure, exceptions and recovery provisions; no blanket FRI conclusion"
        for match, ev in _matches(document,
                r"(?:the Tenant[’']s Proportion[’']?\s*(?:means)?).{0,800}?in the case of all other items of Expenditure\s+\d+(?:\.\d+)?%", 1):
            row["service_charge"].append({"text": match.group(0), "evidence": [ev],
                "basis": "Stated allocation; check variation powers, budget, recovery conditions and actual collections"})

        excluded = _matches(document,
            r"agree that the provisions of sections 24 to 28 of the LTA 1954 are excluded.{0,90}?\.", 1)
        if excluded:
            row["security"] = {"position": "Lease states LTA 1954 sections 24–28 excluded",
                               "verified_procedure": False, "evidence": [excluded[0][1]],
                               "action": "Check the warning notice and tenant declaration; the clause alone does not validate the procedure."}

        uncertain = ([row["term"]] if row["term"] and row["term"]["uncertain"] else []) + [b for b in row["breaks"] if b["uncertain"]]
        if uncertain:
            finding(document, "dates", "Edited lease dates need confirmation",
                    "Conflicting month words or incomplete date fields remain in the supplied lease.",
                    "An automatically calculated expiry or break deadline could be wrong.",
                    "The report preserves the printed date wording instead of choosing a date silently.",
                    "Have the conveyancer confirm the executed commencement, expiry and break dates against the signed document.",
                    [ev for item in uncertain for ev in item["evidence"]])
        leases.append(row)
    return {"leases": leases, "findings": findings}
