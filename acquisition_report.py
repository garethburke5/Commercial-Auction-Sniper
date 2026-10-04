"""Readable, printable acquisition snapshot/full-review renderer. All evidence escaped."""
from html import escape
from acquisition_intelligence import money,SECTIONS
from legal_pack_report import REVIEW_CSS

def render(report,standalone=False):
    e=lambda v:escape(str(v or ''))
    def sources(items):
        return ''.join('<details class="ai-evidence"><summary>'+e(x.get('document'))+' · page '+e(x.get('page') or 'not recorded')+'</summary><blockquote>'+e(x.get('excerpt'))+'</blockquote></details>' for x in items)
    def finding(f):
        return '<article class="ai-finding"><span class="ai-level">'+e(f['severity'])+'</span><h3>'+e(f['title'])+'</h3>'+''.join('<p><b>'+label+'</b> '+e(f.get(k))+'</p>' for k,label in [('found','What we found.'),('why','Why it matters.'),('meaning','What it means.'),('impact','Financial impact.'),('next_step','Next step.')] if f.get(k))+sources(f.get('evidence',[]))+'</article>'
    snap=report.get('access')=='snapshot';out=['<style>'+REVIEW_CSS+'''
.ai-findings{display:grid;gap:16px}.ai-finding{padding:22px;background:#fff;border:1px solid #d4dfe6;border-radius:9px}.ai-level{font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#496174}.ai-numbers{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.ai-number{padding:16px;background:#edf5f2;border-radius:9px}.ai-number strong{font-size:1.25rem;display:block;color:#006c5d}.ai-deep{border:2px solid #138474;border-radius:12px;padding:22px;background:#f3faf7}.ai-evidence{font-size:.83rem}.ai-evidence blockquote{max-height:none}.ai-steps{display:flex;gap:10px;flex-wrap:wrap}.ai-steps a{padding:6px;border-bottom:1px solid #a7bcbf}.ai-question{padding:16px;background:#f2f5f8;margin:12px 0}.ai-docs{width:100%;border-collapse:collapse}.ai-docs td,.ai-docs th{border-bottom:1px solid #d6e1e5;padding:10px;text-align:left}.ai-paywall{padding:24px;background:#163946;color:white!important;border-radius:10px;margin:25px 0}.ai-paywall h2,.ai-paywall p{color:white!important}.ai-paywall a{color:#a7efdc!important}
@media(max-width:650px){.ai-numbers{grid-template-columns:1fr 1fr}.ai-finding,.ai-deep{padding:16px}.ai-docs,.ai-docs tbody,.ai-docs tr,.ai-docs td{display:block}.ai-docs thead{display:none}}
</style><article class="dd-report"><p class="dd-kicker">AUCTION SNIPER / ACQUISITION INTELLIGENCE</p><h1>'''+e(report['property'])+'</h1><p class="dd-muted">'+('Free acquisition snapshot' if snap else 'Full acquisition review')+' · '+e(report['created_at'][:10])+' · '+e(report['report_id'])+'</p>',
    '<h2>What you are buying</h2><p>'+e(report['what_you_are_buying'])+'</p><div class="ai-numbers">']
    for label,v in [('Guide price',money(report.get('guide'))),('Current annual rent',money(report.get('rent'))),('Tenant',report.get('tenant') or 'Not established'),('Tenure',report.get('tenure') or 'Not established'),('Lease',report.get('lease')),('Completion',report.get('completion'))]:out.append('<div class="ai-number"><small>'+label+'</small><strong>'+e(v)+'</strong></div>')
    out.append('</div><h2>The numbers</h2><div class="ai-numbers">')
    for calc in report.get('calculations',[]):out.append('<div class="ai-number"><h3>'+e(calc['label'])+'</h3><strong>'+e(calc['value'])+'</strong><p>'+e(calc['working'])+'</p><small>'+e(calc.get('basis',''))+'</small>'+sources(calc.get('evidence',[]))+'</div>')
    out.append('</div><p><b>VAT / TOGC:</b> '+e(report.get('vat'))+'</p><h2>Our first-pass view</h2><p>'+e(report.get('first_pass'))+'</p>')
    if snap:
        out.extend(finding(f) for f in report['findings'])
        if report.get('deep_dive'):out.append('<section class="ai-deep"><p class="dd-kicker">AUCTION SNIPER DEEP DIVE</p>'+finding(report['deep_dive'])+'</section>')
        out.append('<section class="ai-paywall"><h2>Go deeper before you bid</h2><p>'+str(report.get('additional_findings',0))+' additional consolidated findings, the full document register, transaction evidence and remaining questions are available in the full review.</p><p>Full-review purchases open when secure accounts and payments are activated. You have not been charged.</p></section>')
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
