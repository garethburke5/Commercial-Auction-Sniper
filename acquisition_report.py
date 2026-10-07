"""Readable, printable acquisition snapshot/full-review renderer. All evidence escaped."""
from html import escape
from acquisition_intelligence import money,SECTIONS
from legal_pack_report import REVIEW_CSS

def _render_legacy(report,standalone=False):
    e=lambda v:escape(str(v or ''))
    def sources(items):
        return ''.join('<details class="ai-evidence"><summary>'+e(x.get('document'))+' · page '+e(x.get('page') or 'not recorded')+'</summary><blockquote>'+e(x.get('excerpt'))+'</blockquote></details>' for x in items)
    def finding(f):
        return '<article class="ai-finding"><span class="ai-level">'+e(f['severity'])+'</span><h3>'+e(f['title'])+'</h3>'+''.join('<p><b>'+label+'</b> '+e(f.get(k))+'</p>' for k,label in [('found','What we found.'),('why','Why it matters.'),('meaning','What it means.'),('impact','Financial impact.'),('next_step','Next step.')] if f.get(k))+sources(f.get('evidence',[]))+'</article>'
    engine=report.get('engine') or {}
    engine_label=(' · '+e(engine.get('release'))+' / '+e(engine.get('build'))) if engine else ''
    snap=report.get('access')=='snapshot';out=['<style>'+REVIEW_CSS+'''
.ai-findings{display:grid;gap:16px}.ai-finding{padding:22px;background:#fff;border:1px solid #d4dfe6;border-radius:9px}.ai-level{font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#496174}.ai-numbers{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.ai-number{padding:16px;background:#edf5f2;border-radius:9px}.ai-number strong{font-size:1.25rem;display:block;color:#006c5d}.ai-deep{border:2px solid #138474;border-radius:12px;padding:22px;background:#f3faf7}.ai-evidence{font-size:.83rem}.ai-evidence blockquote{max-height:none}.ai-steps{display:flex;gap:10px;flex-wrap:wrap}.ai-steps a{padding:6px;border-bottom:1px solid #a7bcbf}.ai-question{padding:16px;background:#f2f5f8;margin:12px 0}.ai-docs{width:100%;border-collapse:collapse}.ai-docs td,.ai-docs th{border-bottom:1px solid #d6e1e5;padding:10px;text-align:left}.ai-paywall{padding:24px;background:#163946;color:white!important;border-radius:10px;margin:25px 0}.ai-paywall h2,.ai-paywall p{color:white!important}.ai-paywall a{color:#a7efdc!important}
@media(max-width:650px){.ai-numbers{grid-template-columns:1fr 1fr}.ai-finding,.ai-deep{padding:16px}.ai-docs,.ai-docs tbody,.ai-docs tr,.ai-docs td{display:block}.ai-docs thead{display:none}}
</style><article class="dd-report"><p class="dd-kicker">AUCTION SNIPER / ACQUISITION INTELLIGENCE</p><h1>'''+e(report['property'])+'</h1><p class="dd-muted">'+('Free acquisition snapshot' if snap else 'Full acquisition review')+' · '+e(report['created_at'][:10])+' · '+e(report['report_id'])+engine_label+'</p>',
    '<h2>What you are buying</h2><p>'+e(report['what_you_are_buying'])+'</p><div class="ai-numbers">']
    for label,v in [('Guide price',money(report.get('guide'))),('Current annual rent',money(report.get('rent'))),('Tenant',report.get('tenant') or 'Not established'),('Tenure',report.get('tenure') or 'Not established'),('Lease',report.get('lease')),('Completion',report.get('completion'))]:out.append('<div class="ai-number"><small>'+label+'</small><strong>'+e(v)+'</strong></div>')
    out.append('</div><h2>The numbers</h2><div class="ai-numbers">')
    for calc in report.get('calculations',[]):out.append('<div class="ai-number"><h3>'+e(calc['label'])+'</h3><strong>'+e(calc['value'])+'</strong><p>'+e(calc['working'])+'</p><small>'+e(calc.get('basis',''))+'</small>'+sources(calc.get('evidence',[]))+'</div>')
    out.append('</div><p><b>VAT / TOGC:</b> '+e(report.get('vat'))+'</p><h2>Our first-pass view</h2><p>'+e(report.get('first_pass'))+'</p>')
    if snap:
        out.extend(finding(f) for f in report['findings'])
        if report.get('deep_dive'):out.append('<section class="ai-deep"><p class="dd-kicker">AUCTION SNIPER DEEP DIVE</p>'+finding(report['deep_dive'])+'</section>')
        remaining=report.get('additional_findings',0)
        depth=(str(remaining)+' additional consolidated findings, plus the ' if remaining else 'The ')
        out.append('<section class="ai-paywall"><h2>Go deeper before you bid</h2><p>'+depth+'full document register, transaction evidence and remaining questions are available in the full review.</p><p>Full-review purchases open when secure accounts and payments are activated. You have not been charged.</p></section>')
    else:
        market=report.get('market_context') or {}
        if market.get('history') or market.get('comparables'):
            out.append('<section><h2>Auction Sniper Market Context</h2><p>Guide prices are asking evidence, not completed sales. Historical appearances retain their own dates and sources.</p>')
            for label,key in [('Previous appearances','history'),('Comparable auction evidence','comparables')]:
                if market.get(key):out.append('<h3>'+label+'</h3>')
                for r in market.get(key,[]):
                    out.append('<article class="ai-question"><h3>'+e(r.get('address'))+'</h3><p>'+e(r.get('auction_date'))+' · '+e(r.get('source'))+' · Lot '+e(r.get('lot_number'))+'</p><p>Guide: '+money(r.get('guide_price'))+' · Sale result: '+money(r.get('sale_price'))+'</p><p>'+e('; '.join(r.get('why',[])))+'</p></article>')
            out.append('</section>')
        out.append('<nav class="ai-steps">'+''.join('<a href="#ai-'+sid+'">'+e(title)+'</a>' for sid,title in SECTIONS[3:])+'</nav>')
        for sid,title in SECTIONS[3:]:
            out.append('<section id="ai-'+sid+'"><h2>'+e(title)+'</h2>')
            if sid=='covenant':
                out.append('<p><b>Who owes the rent?</b> '+e(report.get('tenant') or 'The exact legal tenant is not established')+'. A trading name or group brand alone is not the lease covenant.</p>')
                if report.get('company_number'):out.append('<p>Company number '+e(report['company_number'])+'. <a href="https://find-and-update.company-information.service.gov.uk/company/'+e(report['company_number'])+'">Official Companies House record ↗</a></p>')
                out.append('<p>Current financial strength, group support and guarantees must be evidenced separately. An active registration is not a credit rating.</p>'+sources(report.get('tenant_evidence',[])))
                if report.get('covenant'):out.append('<p>'+e(report['covenant'].get('interpretation'))+'</p>')
            elif sid=='lease':
                out.append('<p>Each rent remains attached to the document that states it. A document’s age alone does not prove that it is historic or superseded.</p>')
                for record in report.get('lease_reconciliation',[]):
                    out.append('<article class="ai-question"><h3>'+e(record['document'])+'</h3><p><b>Document date:</b> '+e(record.get('document_date') or 'Not established')+' · '+e(record.get('date_basis') or '')+'</p><p><b>Effect:</b> '+e(record['temporal_status'])+'</p><p><b>Rent in this document:</b> '+e(', '.join(money(r)+' p.a.' for r in record['rent_amounts']) or 'Not recovered')+'</p><p>'+e(record['term'])+'</p>'+sources(record['evidence'])+'</article>')
                out.extend(finding(f) for f in report['findings'] if f['section']=='lease')
            elif sid=='cpse':out.append('<p>'+e(report['cpse'])+'</p>')
            elif sid=='opportunities':
                out.extend(finding(f) for f in report.get('opportunities',[]))
                if not report.get('opportunities'):out.append('<p>No additional opportunity is sufficiently evidenced to promote as a benefit. Planning references alone do not establish development potential.</p>')
            elif sid=='unknowns':out.append('<ul>'+''.join('<li>'+e(s)+'</li>' for s in report.get('unknowns',[]))+'</ul>')
            elif sid=='questions':
                for q in report.get('questions',[]):out.append('<article class="ai-question"><h3>'+e(q['question'])+'</h3><p><b>Who:</b> '+e(q['who'])+'</p><p><b>Why:</b> '+e(q['why'])+'</p><p><b>Already established:</b> '+e(q['established'])+'</p></article>')
            elif sid=='evidence':
                out.append('<p>'+e(report.get('coverage',{}).get('pages'))+' pages processed · '+e(report.get('coverage',{}).get('ocr_pages'))+' OCR pages · '+e(report.get('coverage',{}).get('unread_pages'))+' unread pages.</p><table class="ai-docs"><thead><tr><th>Document</th><th>Type / status</th><th>Pages / processing</th></tr></thead><tbody>')
                for d in report.get('documents',[]):out.append('<tr><td>'+e(d['document'])+'</td><td>'+e(d.get('type'))+'<br>'+e(d.get('temporal_status'))+'</td><td>'+e(d.get('pages'))+' · '+e(d.get('status'))+'</td></tr>')
                out.append('</tbody></table>')
                for sec in report.get('evidence_review',{}).get('sections',[]):
                    if sec.get('items'):out.append('<details><summary>'+e(sec['title'])+' · source extracts</summary>'+''.join(sources(f.get('evidence',[])) for f in sec['items'])+'</details>')
            else:
                selected=[f for f in report['findings'] if f['section']==sid]
                out.extend(finding(f) for f in selected)
                if not selected:out.append('<p>No specific conclusion is established in this section. Review the source extracts and document coverage before relying on an absence of findings.</p>')
            out.append('</section>')
    out.append('<footer>'+e(report['disclaimer'])+' GIY: Gross Initial Yield. FRI: Full Repairing and Insuring. TOGC: Transfer of a Going Concern. CPSE: Commercial Property Standard Enquiries.</footer></article>')
    html=''.join(out)
    if standalone:html='<!doctype html><html lang="en-GB"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+e(report['property'])+' — Acquisition Intelligence</title><body>'+html+'</body></html>'
    return html


def _source_label(evidence):
    """Short source anchors for the commercial report; extracts stay in the appendix."""
    return '; '.join(dict.fromkeys(
        str(item.get('document') or 'Source') +
        (', p. ' + str(item['page']) if item.get('page') else '')
        for item in (evidence or [])))


def commercial_brief(report):
    """Return an editorial brief or a conservative, source-bound standard summary.

    The brief is a paid projection. It must never be included in a free snapshot.
    This function deliberately does not truncate findings to meet a page target.
    """
    if report.get('access') == 'snapshot':
        raise ValueError('The commercial brief requires a full report')
    if report.get('commercial_brief'):
        return report['commercial_brief']
    findings = report.get('findings', [])
    actionable = [f for f in findings if f.get('severity') != 'INFORMATION']
    risk_findings = actionable or findings
    calc = report.get('calculations', [])
    numbers = [
        {'label': 'Guide price', 'value': money(report.get('guide')) +
         (' to ' + money(report['guide_upper']) if report.get('guide_upper') else ''),
         'basis': 'Auction particulars'},
        {'label': 'Published annual rent', 'value': money(report.get('rent')),
         'basis': 'Payment and operative lease terms require reconciliation'},
        {'label': 'Tenure', 'value': report.get('tenure') or 'Not established',
         'basis': 'Confirm the estate and plan'},
    ]
    numbers.extend({'label': c.get('label'), 'value': c.get('value'),
                    'basis': c.get('working')} for c in calc
                   if c.get('label') in ('Gross Initial Yield (GIY)', 'Deposit at guide',
                                         'Quantified additional costs'))
    catalogue_date = report.get('catalogue_as_of')
    published_source = 'Auction tenancy schedule' + (' as at ' + str(catalogue_date)[:10] if catalogue_date else '')
    income = [{'unit': r.get('Address') or 'Published demise',
               'tenant': 'Published: ' + str(r.get('Present Lessee') or 'Not stated'),
               'rent': (money(r.get('Current Rent (PA)')) if isinstance(r.get('Current Rent (PA)'), (int, float))
                        else r.get('Current Rent (PA)') or 'Not stated'),
               'terms': r.get('Lease Details') or 'Terms not stated',
               'source': published_source}
              for r in report.get('tenancy_schedule', [])]
    lease_details = report.get('lease_details') or []
    if not income and lease_details:
        income = [{'unit': r.get('document'), 'tenant': r.get('tenant') or 'Not established',
                   'rent': money(r.get('annual_rent')),
                   'terms': (r.get('term') or {}).get('text') or r.get('interest') or 'Term not recovered',
                   'source': _source_label(r.get('evidence'))}
                  for r in lease_details]
    if not income:
        income = [{'unit': r.get('document'), 'tenant': 'See lease party evidence',
                   'rent': ', '.join(money(v) + ' p.a.' for v in r.get('rent_amounts', [])) or 'Not recovered',
                   'terms': r.get('term') or r.get('temporal_status'),
                   'source': _source_label(r.get('evidence'))}
                  for r in report.get('lease_reconciliation', [])]
    if not income:
        income = [{'unit': 'Property', 'tenant': report.get('tenant') or 'Not established',
                   'rent': money(report.get('rent')), 'terms': report.get('lease'),
                   'source': _source_label(report.get('tenant_evidence'))}]
    income_commentary = []
    if report.get('tenancy_schedule'):
        income_commentary.append('The table reproduces the auctioneer’s published tenancy schedule. '
                                 'Published lessees, rents and dates require reconciliation with the executed '
                                 'lease for each demise, later variations and current payment records.')
    for lease in lease_details:
        notes, evidence = [], list(lease.get('evidence') or [])
        if lease.get('tenant'):
            notes.append('Lease tenant: ' + str(lease['tenant']) + '.')
        for item in lease.get('breaks', []):
            notes.append(str(item.get('party') or 'Lease') + ' break: ' + str(item.get('date_raw') or 'date unresolved') +
                         ('; ' + str(item['notice_raw']) if item.get('notice_raw') else '') +
                         '. Check all conditions and notices.' + (' The printed date is uncertain.' if item.get('uncertain') else ''))
            evidence.extend(item.get('evidence') or [])
        reviews = lease.get('reviews') or []
        if reviews:
            notes.append('Review: ' + ' '.join(str(item.get('text') or '') for item in reviews))
            evidence.extend(item for review in reviews for item in review.get('evidence', []))
        if lease.get('review_method'):
            notes.append(str(lease['review_method']) + '.')
        if lease.get('repairs'):
            notes.append(lease.get('repair_basis') or 'Repair and recovery clauses require review against the demised extent and retained structure.')
            evidence.extend(item for repair in lease['repairs'] for item in repair.get('evidence', []))
        security = lease.get('security') or {}
        if security:
            notes.append(str(security.get('position') or '') + '. ' + str(security.get('action') or ''))
            evidence.extend(security.get('evidence') or [])
        ground_rent = lease.get('ground_rent') or {}
        if ground_rent:
            notes.append('Residential long lease: ' + str(ground_rent.get('basis') or 'Confirm current ground rent and review dates') + '.')
            evidence.extend(ground_rent.get('evidence') or [])
        if notes:
            income_commentary.append(str(lease.get('document') or 'Lease') + ' — ' + ' '.join(notes) +
                                     (' Source: ' + _source_label(evidence) + '.' if evidence else ''))
    income_commentary.append('Rent in this document is evidence of its stated terms, not proof of current payment. '
                             'Different demises and lease dates must be reconciled before rents are aggregated.')
    risks = [{'priority': 'High' if 'CRITICAL' in f.get('severity', '') else 'Check',
              'title': f.get('title'), 'finding': ' '.join(str(f.get(k) or '') for k in
                                                        ('found', 'impact')).strip(),
              'action': f.get('next_step'), 'source': _source_label(f.get('evidence'))}
             for f in risk_findings]
    coverage = report.get('coverage', {})
    source_notes = [f"{coverage.get('pages', 'Unrecorded')} pages processed; "
                    f"{coverage.get('ocr_pages', 0)} OCR pages; "
                    f"{coverage.get('unread_pages', 0)} unread pages.",
                    'Source extracts and the document register are available in the online evidence appendix.']
    source_notes.extend(report.get('unknowns', []))
    listing_status = str(report.get('listing_status') or '').upper()
    terminal = any(token in listing_status for token in ('SOLD', 'WITHDRAWN', 'UNSOLD', 'POSTPONED'))
    status = (listing_status + ' — auction pack review') if terminal else 'Acquisition review'
    summary = report.get('what_you_are_buying', '')
    if terminal:
        summary = ('Catalogue status: ' + listing_status + '. ' +
                   ('Auction date: ' + str(report['auction_date']) + '. ' if report.get('auction_date') else '') +
                   'This review records the stated auction pack and does not establish a currently available purchase. ' + summary)
    elif report.get('auction_date'):
        source_notes.insert(0, 'Auction date: ' + str(report['auction_date']) + '. Confirm current availability and any addendum before relying on the pack.')
    if catalogue_date:
        source_notes.insert(0, 'Catalogue evidence captured ' + str(catalogue_date) + '; source status and terms may subsequently change.')
    return {
        'as_of': str(report.get('created_at', ''))[:10],
        'status': status,
        'summary': summary,
        'conclusion': ('Material enquiries remain open. Resolve the prioritised checks and confirm the '
                       'complete acquisition budget before making an unconditional commitment.'
                       if actionable else
                       'Assess the evidenced income and acquisition costs alongside the outstanding '
                       'source checks. This report does not establish an investment value or recommend a bid.'),
        'key_figures': numbers,
        'income_rows': income,
        'income_commentary': income_commentary,
        'cost_rows': [{'item': c.get('label'), 'amount': money(c.get('amount')),
                       'basis': c.get('basis') or _source_label(c.get('evidence'))}
                      for c in report.get('costs', [])],
        'financial_commentary': [report.get('vat', ''), report.get('completion', ''),
                                'A deposit is part of the purchase price. Allow separately for transaction tax, '
                                'your advisers, financing, voids and works; the quantified fees are not an all-in budget.'],
        'sensitivity_rows': [], 'risks': risks,
        'checks': [{'who': q.get('who'), 'action': q.get('question'), 'source': ''}
                   for q in report.get('questions', [])],
        'source_notes': source_notes, 'scope': report.get('disclaimer', '')}


COMPACT_CSS = '''
.acq-report{font-family:Arial,Helvetica,sans-serif;color:#17232a;background:#fff;max-width:920px;margin:0 auto;line-height:1.42;font-size:15px}
.acq-report *{box-sizing:border-box}.acq-report h1,.acq-report h2,.acq-report h3{color:#000;line-height:1.15}
.acq-report h1{font-size:30px;margin:14px 0 12px;font-weight:700;letter-spacing:-.025em}
.acq-report h2{font-size:23px;margin:0 0 17px;letter-spacing:-.015em}.acq-report h3{font-size:16px;margin:17px 0 6px}
.acq-report p{margin:0 0 10px}.acq-kicker{font-size:11px;letter-spacing:.16em;font-weight:700;margin-bottom:9px!important}
.acq-meta,.acq-source,.acq-small{color:#52616b;font-size:12px}.acq-meta{margin-bottom:22px!important}
.acq-page{padding:30px 36px;border-bottom:1px solid #d9d9d9}.acq-intro{font-size:16px;line-height:1.48}
.acq-status{font-weight:700}.acq-key-table,.acq-table{border-collapse:collapse;width:100%;margin:14px 0 15px;table-layout:fixed}
.acq-table th,.acq-table td,.acq-key-table th,.acq-key-table td{border:1px solid #d9d9d9;padding:10px 11px;text-align:left;vertical-align:middle;overflow-wrap:anywhere}
.acq-table th{background:#203747;color:white;font-size:12px;font-weight:700}.acq-table tr:nth-child(even) td{background:#f3f5f7}
.acq-key-table th{width:31%;background:#f3f5f7;font-size:13px}.acq-key-table strong{display:block;font-size:19px;color:#17232a;margin:1px 0 4px}
.acq-table td{font-size:13px}.acq-table .acq-amount{white-space:nowrap;text-align:right}.acq-source{display:block;margin-top:5px;line-height:1.3}
.acq-risk{break-inside:avoid;margin:0 0 15px}.acq-risk h3{margin:0 0 5px}.acq-priority{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:#805119}
.acq-priority-list{padding-left:20px;margin:10px 0}.acq-priority-list li{margin:0 0 7px}.acq-check{margin:0 0 13px;break-inside:avoid}
.acq-check strong{display:block;margin-bottom:3px}.acq-notes{padding-left:18px;font-size:12px;line-height:1.38}.acq-notes li{margin-bottom:6px}
.acq-disclaimer{font-size:11px;color:#52616b;margin-top:14px!important}.acq-appendix{margin:24px 0;padding:20px 36px;border:1px solid #d9d9d9}
.acq-appendix>summary{font-weight:700;cursor:pointer}.acq-appendix details{margin:12px 0}.acq-appendix blockquote{font-size:13px;white-space:pre-wrap;margin:10px 0;padding:10px 15px;border-left:3px solid #bac7cd}
.acq-appendix .acq-table{table-layout:auto}.acq-engine{font-size:10px;color:#65737c;margin-top:12px!important}
@media(max-width:650px){.acq-page{padding:24px 18px}.acq-report h1{font-size:25px}.acq-table th,.acq-table td{padding:8px 6px;font-size:12px}.acq-table{table-layout:auto}.acq-table .acq-amount{white-space:normal}.acq-appendix{padding:18px}.acq-key-table th{width:38%}}
@page{size:A4;margin:16mm 17mm 16mm}
@media print{
 html,body{margin:0!important;padding:0!important;background:#fff!important}
 .acq-report{max-width:none;font-size:9.5pt;line-height:1.34;color:#000}
 .acq-page{padding:0;border:0;break-after:page;page-break-after:always}
 .acq-page:last-of-type{break-after:auto;page-break-after:auto}
 .acq-report h1{font-size:23pt;margin:8pt 0}.acq-report h2{font-size:18pt;margin:0 0 12pt}.acq-report h3{font-size:11pt;margin-top:10pt}
 .acq-intro{font-size:10.5pt}.acq-report p{margin-bottom:7pt}.acq-meta{font-size:8pt;margin-bottom:14pt!important}.acq-kicker{font-size:8pt}
 .acq-table th,.acq-table td{font-size:8.5pt;padding:6pt 7pt}.acq-key-table th{font-size:9pt}.acq-key-table th,.acq-key-table td{padding:6pt 8pt}
 .acq-key-table strong{font-size:14pt}.acq-table,.acq-key-table{margin:10pt 0 12pt}.acq-table tr{break-inside:avoid}.acq-table thead{display:table-header-group}
 .acq-source,.acq-small,.acq-notes{font-size:8pt}.acq-risk{margin-bottom:11pt}.acq-risk h3{margin-top:0}.acq-check{margin-bottom:9pt}
 .acq-appendix{display:none!important}.acq-disclaimer{font-size:7.5pt}.acq-engine{font-size:7pt}
 *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
'''


def render(report, standalone=False):
    """Concise paid report, with complete evidence available separately on screen."""
    if report.get('access') == 'snapshot':
        return _render_legacy(report, standalone=standalone)
    brief = commercial_brief(report)
    e = lambda value: escape(str(value if value is not None else ''))
    p = lambda value, cls='': '<p' + (' class="' + cls + '"' if cls else '') + '>' + e(value) + '</p>' if value else ''
    def table(headers, rows, widths=None):
        if not rows:
            return ''
        return ('<table class="acq-table">' +
                ('<colgroup>' + ''.join('<col style="width:' + str(w) + '%">' for w in widths) + '</colgroup>' if widths else '') +
                '<thead><tr>' + ''.join('<th scope="col">' + e(h) + '</th>' for h in headers) +
                '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + cell + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody></table>')
    def source(value):
        return '<span class="acq-source">' + e(value) + '</span>' if value else ''
    title = report.get('property') or 'Property acquisition report'
    out = ['<style>' + COMPACT_CSS + '</style><article class="acq-report">',
           '<section class="acq-page" id="decision"><p class="acq-kicker">AUCTION SNIPER · ACQUISITION INTELLIGENCE</p>',
           '<h1>' + e(title) + '</h1>', p(str(brief.get('as_of') or '') + ' · ' + str(brief.get('status') or 'Acquisition review'), 'acq-meta'),
           p(brief.get('summary'), 'acq-intro'), '<h3>Acquisition conclusion</h3>', p(brief.get('conclusion')),
           '<table class="acq-key-table"><tbody>']
    for number in brief.get('key_figures', []):
        out.append('<tr><th scope="row">' + e(number.get('label')) + '</th><td><strong>' + e(number.get('value')) + '</strong>' + source(number.get('basis')) + '</td></tr>')
    out.append('</tbody></table>')
    risks = brief.get('risks', [])
    if risks:
        out.append('<h3>Decision priorities</h3><ol class="acq-priority-list">' + ''.join('<li><b>' + e(r.get('title')) + '.</b> ' + e(r.get('action')) + '</li>' for r in risks[:3]) + '</ol>')
    out.extend([p(brief.get('scope'), 'acq-disclaimer'), '</section>',
                '<section class="acq-page" id="income"><h2>Income and lease terms</h2>'])
    rows = [[e(r.get('unit')) + source(r.get('source')), e(r.get('tenant')), e(r.get('rent')), e(r.get('terms'))] for r in brief.get('income_rows', [])]
    out.append(table(['Accommodation', 'Legal tenant', 'Annual rent', 'Terms and qualifications'], rows, [22, 22, 14, 42]))
    out.extend(p(text) for text in brief.get('income_commentary', []) if text)
    out.extend(['</section><section class="acq-page" id="financials"><h2>Price and acquisition costs</h2>',
                table(['Cost or cash item', 'Amount', 'Basis and treatment'], [[e(r.get('item')), e(r.get('amount')), e(r.get('basis'))] for r in brief.get('cost_rows', [])], [32, 20, 48])])
    out.extend(p(text) for text in brief.get('financial_commentary', []) if text)
    if brief.get('sensitivity_rows'):
        out.append('<h3>Income sensitivity</h3>')
        out.append(table(['Scenario', 'Annual rent', 'Gross yield', 'Interpretation'], [[e(r.get('scenario')), e(r.get('rent')), e(r.get('yield')), e(r.get('meaning'))] for r in brief['sensitivity_rows']], [24, 17, 16, 43]))
    out.append('</section><section class="acq-page" id="risks"><h2>Prioritised acquisition risks</h2>')
    if not risks:
        out.append(p('No specific risks were established by this review. Absence of an extracted finding is not a clean legal or condition opinion.'))
    for i, risk in enumerate(risks, 1):
        out.extend(['<section class="acq-risk"><h3>' + e(i) + ' ' + e(risk.get('title')) + '</h3>',
                    p(risk.get('priority'), 'acq-priority'), p(risk.get('finding')),
                    p(risk.get('action')), source(risk.get('source')), '</section>'])
    out.append('</section><section class="acq-page" id="checks"><h2>Before an unconditional commitment</h2>')
    for check in brief.get('checks', []):
        out.append('<div class="acq-check"><strong>' + e(check.get('who')) + '</strong>' + p(check.get('action')) + source(check.get('source')) + '</div>')
    out.extend(['<h3>Evidence and scope</h3><ul class="acq-notes">',
                ''.join('<li>' + e(note) + '</li>' for note in brief.get('source_notes', [])), '</ul>',
                '<h3>Acquisition conclusion</h3>', p(brief.get('conclusion')), p(brief.get('scope') or report.get('disclaimer'), 'acq-disclaimer')])
    engine = report.get('engine') or {}
    out.append(p('Report ' + str(report.get('report_id', '')) +
                 (' · Engine ' + str(engine.get('release', '')) + ' / ' + str(engine.get('build', '')) if engine else ''), 'acq-engine'))
    out.append('</section>')
    # Source evidence is inspectable, but does not turn a printed paid brief into
    # a long extraction dump. It is never present in the free snapshot branch.
    out.append('<details class="acq-appendix"><summary>Source evidence and document register</summary><p class="acq-small">Supporting source extracts. This appendix is excluded from the concise print report.</p>')
    out.append(table(['Document', 'Type and status', 'Pages'], [[e(d.get('document')), e(d.get('type')) + '<br>' + e(d.get('temporal_status')), e(d.get('pages'))] for d in report.get('documents', [])]))
    for record in report.get('lease_reconciliation', []):
        out.append('<details><summary>' + e(record.get('document')) + '</summary>' + p('Rent in this document: ' + (', '.join(money(v) + ' p.a.' for v in record.get('rent_amounts', [])) or 'Not recovered')) + p(record.get('term')) + '</details>')
    for finding in report.get('findings', []):
        out.append('<details><summary>' + e(finding.get('title')) + '</summary>' + p(finding.get('found')) + p(finding.get('meaning')))
        for evidence in finding.get('evidence', []):
            out.append(source(_source_label([evidence])) + '<blockquote>' + e(evidence.get('excerpt')) + '</blockquote>')
        out.append('</details>')
    for section in report.get('evidence_review', {}).get('sections', []):
        if not section.get('items'):
            continue
        out.append('<details><summary>' + e(section.get('title')) + ' source extracts</summary>')
        for item in section['items']:
            for evidence in item.get('evidence', []):
                out.append(source(_source_label([evidence])) + '<blockquote>' + e(evidence.get('excerpt')) + '</blockquote>')
        out.append('</details>')
    market = report.get('market_context') or {}
    for label, key in [('Previous auction appearances', 'history'), ('Comparable auction evidence', 'comparables')]:
        if market.get(key):
            out.append('<details><summary>' + label + '</summary><p>Guide prices are asking evidence, not completed sales. Each appearance retains its own date and source.</p>')
            out.append(table(['Property and date', 'Source', 'Guide', 'Sale result'],
                             [[e(r.get('address')) + source(r.get('auction_date')), e(r.get('source')) + source('Lot ' + str(r.get('lot_number') or 'not recorded')), e(money(r.get('guide_price'))), e(money(r.get('sale_price')))]
                              for r in market[key]]))
            out.append('</details>')
    out.append('</details></article>')
    html = ''.join(out)
    if standalone:
        html = '<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>' + e(title) + ' Acquisition Intelligence</title></head><body>' + html + '</body></html>'
    return html
