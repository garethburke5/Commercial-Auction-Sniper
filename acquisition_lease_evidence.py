"""Narrow, document-scoped lease facts for acquisition reports.

Each letting stays separate. Extracted initial rent is not certified passing rent;
draft dates and scanned amendments remain source wording for a conveyancer to check.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from legal_pack_review import document_pages, norm

MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
DAY = r"\d{1,2}(?:st|nd|rd|th)?"


def document_role(document):
    """Identify supporting instruments from their own opening, not quoted leases.

    A register, variation or licence can contain rent and term wording without
    creating another letting. Keep these documents in the evidence inventory.
    """
    pages = list(_pages(document))
    front = pages[0][1][:1800] if pages else ''
    if re.search(r'official copy.*register of title|official copy of (?:the )?register|A: Property Register|Title number.*Edition date', front, re.I):
        return 'title_register'
    if re.search(r'\bdeed of variation\b', front, re.I):
        return 'variation'
    if re.search(r'\blicen[cs]e\b.{0,100}\balteration', front, re.I):
        return 'alterations_licence'
    if re.search(r'\b(?:deed of assignment|licen[cs]e to assign)\b', front, re.I):
        return 'assignment'
    if re.search(r'\bDear Sirs\b', front, re.I):
        return 'supporting_correspondence'
    return 'lease_candidate'


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
    unknown_month = any(not re.fullmatch(MONTH, m.group(1), re.I) for m in re.finditer(r'\b\d{1,2}\s+([A-Za-z]+)\s+(?:19|20)\d{2}\b', text))
    return bool(unknown_month or re.search(MONTH + r"\s*" + MONTH, text, re.I)
                or re.search(r"\[\s*\]", text)
                or re.search(r"\b(?:tbc|to be confirmed|insert date)\b", text, re.I))


def _rent_substitution(document, rents):
    """Resolve a quoted old rent only with an explicit, bounded replacement.

    The old lease must be a labelled annex, and every competing rent must be
    inside that annex. This does not establish execution, payment or later changes.
    """
    if len(rents) >= 30:
        return None
    pages = list(_pages(document))
    annexes = [(p, text) for p, text in pages if re.search(
        r'\bANNEX\s+\d+\s+(?:Certified\s+)?copy of the Existing Lease\b', text, re.I)]
    if len(annexes) != 1:
        return None
    annex_page, annex_text = annexes[0]
    boundary = annex_page.get('page')
    if not isinstance(boundary, int):
        return None
    head = [(m, ev) for m, ev in rents if isinstance(ev.get('page'), int) and ev['page'] < boundary]
    tail = [(m, ev) for m, ev in rents if isinstance(ev.get('page'), int) and ev['page'] > boundary]
    if len(head) != 1 or not tail or len(head) + len(tail) != len(rents):
        return None
    clause = None
    for page, text in pages:
        if not isinstance(page.get('page'), int) or page['page'] >= boundary:
            continue
        match = re.search(r'\bThis Lease shall reserve the Annual Rent instead of,? and not in addition to,? the Existing Lease Annual Rent\.', text, re.I)
        if match:
            clause = _evidence(document, page, match.group())
    if clause is None or not re.match(r'Annual Rent[’”\'\"]?\s*(?::|means)?\s*(?:rent\s+)?(?:at\s+)?(?:a\s+)?rate of\s+£', head[0][1]['excerpt'], re.I):
        return None
    return {'amount': float(head[0][0].group(1).replace(',', '')),
            'earlier_amounts': sorted({float(m.group(1).replace(',', '')) for m, _ in tail}),
            'evidence': [head[0][1], clause, _evidence(document, annex_page, annex_text)] + [ev for _, ev in tail]}


def _law_society_particulars(document, pages):
    """Recognise the labelled business-lease form, including split year boxes.

    Read only the opening particulars. Annexes and standard guarantee wording
    do not establish another tenancy, a named guarantor or completed execution.
    The rent still goes through the shared competing-amount check below.
    """
    if not pages:
        return {}, []
    page, text = pages[0]
    term_label = r'\bTERM FOR WHICH.{0,12}?THE PROPERTY IS.{0,12}?LEASED\b'
    if not (re.search(r'\bLaw Society\b', text, re.I)
            and re.search(term_label, text, re.I)
            and re.search(r'\bFIRST PAYMENT\b', text, re.I)):
        return {}, []
    fields = {'evidence': []}
    tenant = re.search(r'\bTENANT\s+(.{2,150}?)\s+ADDRESS\b', text)
    if tenant and not re.search(r'\b(?:GUARANTOR|LANDLORD|COMPANY NO)\b', tenant[1]):
        # Registration numbers are identifiers, not part of the tenant name.
        # Retain the original excerpt; do not guess OCR digits in that number.
        fields['tenant'] = re.sub(r'\b(Charity|Limited|Ltd|PLC)\s+(?:No\.?|Number)\s+[\d\s]+$',
                                 r'\1', norm(tenant[1]), flags=re.I)
        fields['evidence'].append(_evidence(document, page, tenant.group()))
    unit = re.search(r'\bPROPERTY\s+(.{5,200}?)\s+shown edged (?:red|blue)\b', text, re.I)
    if unit:
        # A complete printed postcode terminates the address before OCR noise
        # from the form's vertical margin. Preserve the printed postcode itself.
        label = norm(unit[1])
        postcode = re.search(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b', label, re.I)
        fields['demise'] = label[:postcode.end()] if postcode else label
        fields['evidence'].append(_evidence(document, page, unit.group()))
    date_pattern = r'(\d{1,2})(?:st|nd|rd|th)?\s+(' + MONTH + r')\s+(19|20)\s*(\d{2})\b'
    def read_date(match):
        try:
            return datetime.strptime(f'{match[1]} {match[2]} {match[3]}{match[4]}', '%d %B %Y').date()
        except ValueError:
            return None
    dated = re.search(r'\bDATE OF LEASE\s+' + date_pattern, text, re.I)
    if dated and read_date(dated):
        fields['lease_date'] = read_date(dated).strftime('%d %B %Y').lstrip('0')
        fields['lease_date_evidence'] = [_evidence(document, page, dated.group())]
    term = re.search(term_label + r'(.{0,220}?)\bPARKING\b', text, re.I)
    if term:
        start = re.search(r'From\s+and\s+including\s+' + date_pattern, term[1], re.I)
        end = re.search(r'To\s*and\s+including\s+' + date_pattern, term[1], re.I)
        if start and end and read_date(start) and read_date(end) and read_date(end) >= read_date(start):
            ev = _evidence(document, page, term.group())
            fields['term'] = {'text': 'From and including ' + read_date(start).strftime('%d %B %Y').lstrip('0')
                + ' to and including ' + read_date(end).strftime('%d %B %Y').lstrip('0'),
                'uncertain': False, 'evidence': [ev]}
            fields['evidence'].append(ev)
    rent = re.search(r'\bRENT\s+(?:(?!FIRST PAYMENT).){0,180}?\bPounds\b[^\d]{0,16}'
                     r'(\d[\d,]*(?:\.\d{1,2})?)\s*\)\s*a\s+year\b', text, re.I)
    return fields, [(rent, _evidence(document, page, rent.group()))] if rent else []


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
        if re.search(r'licen[cs]e\s+(?:for\s+)?alt(?:s|erations?)\b', document.name, re.I):
            continue
        if getattr(document.doc_type, "value", document.doc_type) != "lease":
            continue
        pages = list(_pages(document))
        text = " ".join(value for _, value in pages)
        if not re.search(r"\b(?:lease|tenant|rent)\b", text, re.I):
            continue
        role = document_role(document)
        if role != 'lease_candidate':
            continue
        row = {"document": document.name, "document_role": role, "evidence": [], "tenant": None,
               "annual_rent": None, "rent_basis": "Lease amount; current collection not certified",
               "term": None, "breaks": [], "reviews": [], "repairs": [], "service_charge": [],
               "security": None, "guarantee": "No separately identified guarantor established",
               "rent_deposit": "No existing deposit established from the lease text"}
        first_page = pages[0] if pages else None
        if first_page:
            page, front = first_page
            dated = re.search(r'(?:(\d{1,2}\s+'+MONTH+r')\s+DATED\s+((?:19|20)\d{2})|DATED\s+(\d{1,2}\s+'+MONTH+r'\s+(?:19|20)\d{2}))',front,re.I)
            if dated:
                row['lease_date'] = norm(dated.group(3) or dated.group(1)+' '+dated.group(2))
                row['lease_date_evidence'] = [_evidence(document,page,dated.group())]

        form, form_rents = _law_society_particulars(document, pages)
        row.update({k: v for k, v in form.items() if k != 'evidence'})
        row['evidence'].extend(form.get('evidence', []))

        parties = _matches(document,
            r"\(2\)\s*([A-Z][A-Z ,.&'’()\-]{2,140}?)\s+of\s+.{3,180}?\(Tenant\)", 1)
        if not parties:
            parties = _matches(document,
                r"\bTenant\s+([A-Z][A-Z ,.&'’()\-]{2,140}?)\s+of\s+.{3,180}?(?=\bLR4\b|\bBackground\b)", 1)
        if parties and not row['tenant']:
            match, ev = parties[0]
            row["tenant"] = norm(match.group(1))
            row["evidence"].append(ev)

        rents = _matches(document,
            r"\b(?:Annual|Initial|Yearly) Rent[’'\"]?\s*(?::|means)?\s*(?:rent\s+)?(?:at\s+)?(?:a\s+)?(?:rate\s+of\s+|the yearly sum of\s+)?[^£.]{0,80}£\s*([\d,]+(?:\.\d{1,2})?)", 30)
        rents += form_rents
        amounts = {float(m.group(1).replace(",", "")) for m, _ in rents}
        substitution = _rent_substitution(document, rents) if len(amounts) > 1 else None
        if substitution:
            row['annual_rent'] = substitution['amount']
            row['rent_substitution'] = substitution
            row['evidence'].extend(substitution['evidence'])
            earlier = ' and '.join(f'£{v:,.0f}' for v in substitution['earlier_amounts'])
            finding(document, 'rent-substitution', 'Lease expressly replaces an earlier rent',
                    f"The lease states annual rent of £{substitution['amount']:,.0f} and expressly replaces the earlier rent. The {earlier} figure is in the attached copy of the old lease.",
                    'The two amounts are not additional rents and should not be added together.',
                    'This establishes the amount stated in this lease, not proof of payment or the absence of later changes.',
                    'Check the signed lease, subsequent changes and payment history.', substitution['evidence'], 'INFORMATION')
        elif len(amounts) == 1:
            row["annual_rent"] = next(iter(amounts))
            row["evidence"].append(rents[0][1])
        elif len(amounts) > 1:
            row['rent_conflicted'] = True
            finding(document, "rent-conflict", "Different lease rent amounts need reconciliation",
                    "; ".join(ev["excerpt"] for _, ev in rents),
                    "An initial or revised rent cannot safely be selected from competing amounts.",
                    "No single annual rent has been assigned to this lease.",
                    "Confirm the operative rent, period, any variation and payment ledger.",
                    [ev for _, ev in rents])

        terms = _matches(document,
            r"\b(?:Contractual Term:\s*)?(?:a\s+)?term (?:of\s+)?(?:\d+|FIVE|TEN|FIFTEEN|TWENTY)[ -]?years from.{0,150}?(?:\]\s*20\d{2}|\b20\d{2}\b)(?:\s+to and including\s+.{0,60}?\b20\d{2}\b)?(?:\.)?", 1)
        if terms and not row['term']:
            row["term"] = {"text": terms[0][0].group(0),
                           "uncertain": _uncertain_date(terms[0][0].group(0)),
                           "evidence": [terms[0][1]]}
            row["evidence"].append(terms[0][1])

        # A defined break date plus the operative tenant/landlord termination power.
        # A contents heading, generic forfeiture or guarantor new-lease clause is not a break.
        date_pattern = r"[‘'’\"“”]?Break Date[’'‘\"“”]?\s*(?::|means)?\s*(\[[^\]]{1,100}\]\s*20\d{2}|" + DAY + r"\s+" + MONTH + r"\s+20\d{2})"
        defined_dates = [(p, m) for p, v in pages for m in re.finditer(date_pattern, v, re.I)]
        unique_dates = {norm(m.group(1)) for _, m in defined_dates}
        for page, value in pages:
            date = re.search(date_pattern, value, re.I)
            date_page = page
            if date is None and len(unique_dates) == 1:
                date_page, date = defined_dates[0]
            power = re.search(r"\b(The\s+)?(Tenant|Landlord|Either party) may (?:terminate|determine) (?:this |the )?[Ll]ease.{0,260}", value, re.I)
            if not (date and power):
                continue
            start = max(0, (date.start() if date_page == page else power.start()) - 100)
            end = min(len(value), power.end() + 1350)
            excerpt = value[start:end]
            notice = re.search(r"(?:not less than|at least)\s+(?:\w+|\d+)\s+(?:months?|weeks?|days?)[^.;]{0,100}", excerpt, re.I)
            condition = re.search(r"(?:Break Notice.{0,60}?shall (?:have|be of) no effect|Subject to clause\s+[\d.]+)[\s\S]{0,1000}", excerpt, re.I)
            ev = _evidence(document, page, excerpt)
            break_evidence = [ev] if date_page == page else [_evidence(document, date_page, date.group(0)), ev]
            item = {"party": power.group(2), "date_raw": norm(date.group(1)),
                    "notice_raw": norm(notice.group(0)) if notice else None,
                    "conditions_raw": norm(condition.group(0)) if condition else None,
                    "uncertain": _uncertain_date(date.group(1)), "evidence": break_evidence}
            row["breaks"].append(item)
            finding(document, "break-" + str(page.get("page")),
                    "Tenant break limits income certainty" if power.group(2).lower() == "tenant" else "Lease break requires review",
                    f"{power.group(2)} break date wording: {item['date_raw']}. " + (item["notice_raw"] or "Notice period not established from this extract."),
                    "The contractual expiry is not the earliest date on which rent may stop.",
                    "Assess letting risk and cash flow at the break; the right remains conditional on the full clause.",
                    "Confirm the effective date, notice deadline, satisfaction of all break conditions and any notice already served.", break_evidence)

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
            r"Landlord shall use reasonable endeavours.{0,320}reasonable state of repair\.(?:\s*Without prejudice.{0,400}?Uninsured Risk\.)?",
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

        # Keep a cap with the full defined charge, rather than interpreting a
        # nearby management-cost cap as a cap on every building expense.
        for page, value in pages:
            cap = re.search(r'\bService Charge:\s*(.{0,1800}?\bcapped at\s*£[\d,.]+.{0,650}?)(?=\bService Media:|\bSigns:|$)', value, re.I)
            if not cap:continue
            ev = _evidence(document, page, cap.group())
            row['service_charge'].append({'text':cap.group(), 'evidence':[ev],
                'basis':'Cap wording retained with its definition; scope, indexation and end date require interpretation.'})
            finding(document,'service-charge-cap','Service-charge recovery includes a cap',
                cap.group(), 'The landlord may be unable to recover all building expenditure from this tenant.',
                'Read the cap alongside the defined services and other occupiers’ contributions; it is not an estimate of repair costs.',
                'Confirm which costs the cap covers, the current indexed limit and when the limit ends.',[ev])

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
