"""Contextual source labels and retained extracts; the audit ledger is untouched.

Private links are supplied only by an authorised delivery route. They contain
report/reference identifiers, never credentials or a capability to bypass login.
"""
from __future__ import annotations
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit, urlencode


def normal(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def public_url(value):
    try:
        value = str(value or '').strip()
        u = urlsplit(value)
        if u.scheme not in ('https', 'http') or not u.hostname or u.username or u.password:
            return None
        if any(ord(c) < 32 for c in value):
            return None
        return value
    except ValueError:
        return None


def document_label(name, report):
    """Keep enough of the real document title to distinguish separate leases."""
    metadata = next((d for d in report.get('documents', []) if d.get('document') == name), {})
    if metadata.get('evidence_label'):
        return normal(metadata['evidence_label'])[:120]
    name = str(name or 'Source document').split('::')[-1].replace('\\', '/').split('/')[-1]
    name = re.sub(r'(?:\.pdf)+$', '', name, flags=re.I)
    name = re.sub(r'^Lot[_ ]\d+[_ ]', '', name, flags=re.I)
    name = name.replace('_', ' ').replace('Absestos', 'Asbestos')
    demise = next((d for d in report.get('investigation', {}).get('demises', [])
                   if d.get('document') == metadata.get('document') and d.get('label')), None)
    if demise and metadata.get('type') == 'lease':
        date = re.search(r'\b\d{2}[.\-]\d{2}[.\-]\d{4}\b', name)
        return 'Lease · ' + normal(demise['label']) + (' · ' + date[0] if date else '')
    name = re.sub(r'^Official Copy (?:of Register - EDOC REGISTRATION -|\(Register\) -)', 'Title register -', name, flags=re.I)
    name = re.sub(r'^Official Copy \(Lease\)', 'Lease', name, flags=re.I)
    name = re.sub(r'^(CPSE\d+) Replies - (.*)', r'Seller replies (\1) · \2', name, flags=re.I)
    name = re.sub(r'^(\d+) - Groundsure Screening.*', r'Groundsure screening · \1', name, flags=re.I)
    name = re.sub(r'^Search Result (\w+) CDWS.*', r'CDWS search · \1', name, flags=re.I)
    return normal(name)


def _restricted(source, report):
    name = source.get('document') or source.get('title')
    metadata = next((d for d in report.get('documents', []) if d.get('document') == name), {})
    related = [p for p in report.get('evidence_review', {}).get('source_pages', [])
               + report.get('investigation', {}).get('evidence', []) if p.get('document') == name]
    return any(d.get('shareable') is False or d.get('evidence_access') == 'restricted'
               for d in (source, metadata, *related))


class EvidenceReferences:
    def __init__(self, report):
        self.report = report
        self.rows = {}
        self.documents = {d.get('document') for d in report.get('documents', [])}
        self.documents.update(p.get('document') for p in report.get('evidence_review', {}).get('source_pages', []))

    def add(self, evidence, context=None):
        grouped = {}
        for source in evidence or []:
            name = source.get('document') or source.get('title')
            url = public_url(source.get('url'))
            if not name and not url:
                continue
            private = name in self.documents or source.get('source_kind') == 'legal_pack' or not url
            key = (name, url, source.get('document_sha256') or source.get('sha256'), private)
            grouped.setdefault(key, []).append(source)
        result = []
        for (name, url, digest, private), sources in grouped.items():
            pages = sorted({int(s['page']) for s in sources if isinstance(s.get('page'), (int, str)) and str(s['page']).isdigit() and int(s['page']) > 0})
            quotes = sorted({normal(s.get('excerpt') or s.get('text')) for s in sources if s.get('excerpt') or s.get('text')})
            identity = [name, url, digest, pages, quotes]
            eid = sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
            restricted = self.rows.get(eid, {}).get('restricted', False) or any(_restricted(s, self.report) for s in sources)
            page_label = ('Page ' if len(pages) == 1 else 'Pages ') + ', '.join(map(str, pages)) if pages else ''
            label = document_label(name, self.report) if private else normal(name or urlsplit(url).hostname)
            row = {'id': eid, 'label': label, 'document': name, 'pages': pages, 'page_label': page_label,
                   'private': private, 'restricted': restricted, 'url': None if private or restricted else url,
                   'evidence': sources, 'href': None, 'available': False}
            row['contexts'] = list(self.rows.get(eid, {}).get('contexts', []))
            if context and context not in row['contexts']:row['contexts'].append(normal(context))
            if private and not restricted:
                row['available'] = bool(evidence_detail(self.report, row)['pages'])
                delivery_context = self.report.get('_evidence_context') or {}
                origin = public_url(delivery_context.get('origin'))
                rid = delivery_context.get('review_id')
                if row['available'] and origin and rid:
                    row['href'] = origin.rstrip('/') + '/due-diligence/?' + urlencode({'review': rid, 'evidence': eid}) + '#supporting-evidence'
            elif row['url']:
                row.update(href=row['url'], available=True)
            # A restricted source remains identifiable, but has no extract/link.
            if eid in self.rows:
                self.rows[eid].update(row)
                row = self.rows[eid]
            self.rows[eid] = row
            result.append(row)
        return result


def evidence_detail(report, row):
    result = {k: row.get(k) for k in ('id', 'label', 'document', 'page_label', 'url', 'private', 'restricted')}
    result['pages'] = []
    if row['restricted'] or not row['private']:
        return result
    retained = report.get('evidence_review', {}).get('source_pages', [])
    if not retained:
        retained = [p for p in report.get('investigation', {}).get('evidence', []) if p.get('source_kind') == 'legal_pack']
    grouped = {}
    for source in row['evidence']:
        page = source.get('page')
        grouped.setdefault(page, []).append(source)
    for page, sources in grouped.items():
        exact = [p for p in retained if p.get('document') == row['document'] and str(p.get('page')) == str(page)
                 and all(not s.get('document_sha256') or p.get('document_sha256') == s['document_sha256'] for s in sources)]
        texts = {normal(p.get('text') or p.get('excerpt')) for p in exact if p.get('text') or p.get('excerpt')}
        page_text = next(iter(texts)) if len(texts) == 1 else ''
        quotes = list(dict.fromkeys(normal(s.get('excerpt') or s.get('text')) for s in sources if s.get('excerpt') or s.get('text')))
        if not quotes and not page_text:
            continue
        # Never match across another page, document, or different document hash.
        matched = [q for q in quotes if q in page_text]
        unmatched = bool(page_text and len(matched) != len(quotes))
        segments = []
        if page_text:
            intervals = []
            for q in matched:
                start = page_text.find(q)
                intervals.append((start, start + len(q)))
            merged = []
            for start, end in sorted(intervals):
                if merged and start <= merged[-1][1]:merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:merged.append((start, end))
            cursor = 0
            for start, end in merged:
                if cursor < start:segments.append({'text': page_text[cursor:start], 'highlighted': False})
                segments.append({'text': page_text[start:end], 'highlighted': True});cursor = end
            if cursor < len(page_text):segments.append({'text': page_text[cursor:], 'highlighted': False})
        result['pages'].append({'number': page, 'extracts': matched if page_text else quotes,
                                'segments': segments, 'ocr': any(p.get('ocr') for p in exact) or any(s.get('ocr') for s in sources),
                                'unmatched_extract': unmatched,
                                'view_kind': 'retained_page_text' if page_text else 'retained_extract'})
    return result


def summary(row):
    return {k: row.get(k) for k in ('id', 'label', 'document', 'pages', 'page_label', 'private', 'restricted', 'url', 'available', 'contexts')}
