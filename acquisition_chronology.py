"""Source-bound lease chronology: document age never proves supersession."""
import re
from datetime import date, datetime


def _norm(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _date(value):
    value = re.sub(r'(\d)(?:st|nd|rd|th)\b', r'\1', value, flags=re.I)
    for fmt in ('%d %B %Y', '%d %b %Y', '%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d'):
        try: return datetime.strptime(value, fmt).date()
        except ValueError: pass
    return None


def lease_chronology(model):
    reviewed = _date(str(model.get('created_at') or '')[:10]) or date.today()
    documents = []; leases = []
    for source in model.get('documents', []):
        doc = dict(source); name = doc['document']
        filename_date = re.search(r'\b(?:19|20)\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}\b', name)
        dated = _date(filename_date.group()) if filename_date else None
        doc['document_date'] = dated.isoformat() if dated else None
        doc['date_basis'] = 'Filename; execution date not independently established' if dated else None
        doc['temporal_status'] = 'SUPPORTING'
        is_lease = 'lease' in str(doc.get('type', '')).lower()
        if is_lease: doc['temporal_status'] = 'CONTINUING EFFECT UNCONFIRMED'
        if re.search(r'\bdraft\b|\bunsigned\b', name, re.I):doc['temporal_status'] = 'DRAFT / UNCERTAIN'
        if is_lease:
            evidence = []; rents = []; terms = []; starts = []; ends = []
            for finding in model.get('findings', []):
                if not finding.get('fact'): continue
                relevant = [e for e in finding.get('evidence', []) if e.get('document') == name]
                if not relevant: continue
                title = finding.get('title', '')
                if title == 'Rent amount recorded in this document':
                    m = re.search(r'£\s*([\d,]+(?:\.\d+)?)', finding.get('summary', ''))
                    if m:rents.append(float(m.group(1).replace(',', '')))
                if title == 'Lease term recorded':
                    terms.append(finding.get('summary', ''))
                    # Do not turn damaged OCR into a precise commencement/expiry.
                    uncertain = re.search(r'visual confirmation|unclear|illegible|uncertain', finding.get('summary', ''), re.I)
                    if not uncertain:
                        for e in relevant:
                            text = _norm(e.get('excerpt'))
                            pattern = r'(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+(?:19|20)\d{2})'
                            for m in re.finditer(r'\b(?:from(?: and including)?|commencement date\s*:?|commencing on)\s+' + pattern, text, re.I):
                                if value := _date(m.group(1)): starts.append(value)
                            for m in re.finditer(r'\b(?:to and including|expir(?:es|ing|y)(?: on| date)?\s*:?|ending on)\s+' + pattern, text, re.I):
                                if value := _date(m.group(1)): ends.append(value)
                if title in ('Lease term recorded', 'Rent amount recorded in this document', 'Tenant named in the lease'):
                    evidence.extend(relevant)
            start = starts[0] if len(set(starts)) == 1 else None
            end = ends[0] if len(set(ends)) == 1 else None
            if doc['temporal_status'] != 'DRAFT / UNCERTAIN':
                if end and end < reviewed:doc['temporal_status'] = 'STATED TERM ENDED / HOLDING OVER UNCONFIRMED'
                elif start and start > reviewed:doc['temporal_status'] = 'FUTURE STATED TERM'
                elif start and end and start <= reviewed <= end:doc['temporal_status'] = 'STATED TERM COVERS REVIEW DATE / VARIATIONS UNCONFIRMED'
            leases.append({'document':name,'document_date':doc['document_date'],'date_basis':doc['date_basis'],
                'temporal_status':doc['temporal_status'],'rent_amounts':sorted(set(rents)),
                'term': ' '.join(dict.fromkeys(terms)) or 'No reliable term recovered',
                'term_start':start.isoformat() if start else None,'term_end':end.isoformat() if end else None,
                'evidence':evidence})
        documents.append(doc)
    return documents, leases
