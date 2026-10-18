"""A reusable five-section investor brief derived from the investigation.

The evidence appendix remains complete. The brief clusters related findings and
makes selection visible; page length is never used as investment approval.
"""
from __future__ import annotations
import re
from acquisition_investigation import cash, ratio
from acquisition_financials import financial_view
from acquisition_editorial import customer_findings, safe_text, lease_events
from acquisition_public_insights import public_insights


def compact(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def repair_summary(lease):
    """Concise source-led allocation; full clauses remain in the appendix."""
    text=' '.join(compact(r.get('text')) for r in lease.get('repairs',[]))
    if re.search(r'Landlord shall use reasonable endeavours',text,re.I):
        result='Landlord uses reasonable endeavours for support/protection and shared services.'
        if 'shall not be obliged' in text:
            result+=' Insured/uninsured-risk exceptions apply.'
        if 'Service Charge:' in text:
            result+=' Tenant pays a fair service-charge proportion; full recovery unproven.'
        return result
    if re.search(r'The Landlord must:.*foundations',text,re.I):
        return 'Landlord has exterior/structure duties including foundations, roof and chimneys. Recovery and tenant shares require the full lease.'
    if re.search(r'Tenant shall pay.*proportion.*external and structural repairs',text,re.I):
        return 'Tenant contributes a fair/reasonable share of building costs, including external and structural repairs. This is not proof of full landlord cost recovery.'
    return text if len(text)<230 else text[:230].rsplit(' ',1)[0]+'... Full wording in the evidence appendix.'


def market_commentary(record):
    """Keep free-form research descriptions from importing unsupported facts."""
    kind=record['kind']
    basis=record.get('price_basis') or record.get('rent_basis') or 'unclassified'
    area=(' Quoted area '+str(record['area_sqft'])+' sq ft.' if record.get('area_sqft') else '')
    if kind=='subject_asking_sale':
        return 'Same-property marketing ask; not an achieved sale or independent valuation.'+area
    if kind=='subject_asking_rent':
        return 'Subject-unit marketing ask; not independent achieved rental evidence.'+area+' Verify layout, date and incentives.'
    return ('Other premises: '+basis+' evidence.'+area+
            ' Adjust for location, size, layout, condition and lease terms; do not transfer its price or rent directly.')


def lease_terms(demise):
    """Keep amended OCR dates out of the investor table; preserve raw evidence."""
    term=demise.get('term') or {}
    text=compact(term.get('text') or 'Term not reliably recovered')
    if term.get('uncertain'):
        text=('Stated five-year term; amended expiry date requires confirmation.'
              if re.search(r'FIVE|5 years',text,re.I) else 'Amended term requires confirmation.')
    else:
        text=compact(re.sub(r'[\[\]]','',re.sub(r'^Contractual Term:\s*','',text)))
        m=re.search(r'FIVE years.*?to and including (.+)',text,re.I)
        if m:text='Five-year term ending '+m[1]
    if demise.get('lease_date'):text='Lease dated '+demise['lease_date']+'. '+text
    for b in demise.get('breaks',[]):
        if b.get('uncertain'):text+=' Break date amended; verify executed wording.'
        else:text+=' '+(b.get('party') or 'Party unconfirmed')+' break: '+compact(re.sub(r'[\[\]]','',b.get('date_raw','')))+'.'
        notice=compact(b.get('notice_raw'))
        if notice:text+=' Notice: '+notice+'.'
        if b.get('conditions_raw'):text+=' Subject to break conditions.'
    return text


def make_brief(report):
    if report.get('access') == 'snapshot':
        raise ValueError('Full report required')
    inv = report['investigation']; ds = inv['demises']
    fs = customer_findings(report); finance = financial_view(report)
    has_pack = bool(report.get('evidence_scope', {}).get('legal_pack_supplied', bool(report.get('documents'))))
    price, rent = finance['price'], finance['rent']
    references, shown = {}, set()

    def refs(evidence):
        ids = []
        for e in evidence or []:
            key = (e.get('url'), e.get('document') or e.get('title'))
            if not any(key):
                continue
            if key not in references:
                references[key] = {'id': f'S{len(references)+1:02}', 'label': key[1] or key[0], 'url': key[0], 'pages': []}
            item = references[key]
            if e.get('page') and str(e['page']) not in item['pages']:
                item['pages'].append(str(e['page']))
            ids.append(item['id'] + (':' + str(e['page']) if e.get('page') else ''))
        return '[' + ', '.join(dict.fromkeys(ids)) + ']' if ids else ''

    def ref_record(r):
        return refs([dict(r['source'], document=r['source']['title'])])

    def p(text, style='body'):
        return {'kind': 'p', 'text': safe_text(text), 'style': style}

    def h(text):
        return {'kind': 'h', 'text': text}

    def table(headers, rows, widths):
        return {'kind': 'table', 'headers': headers, 'rows': rows, 'widths': widths}

    def chart(title, kind, rows, **kwargs):
        return dict(kind='chart', chart=kind, title=title, rows=rows, **kwargs)

    def find(key):
        return next((f for f in fs if f['id'] == key), None)

    def text(f):
        return safe_text(f.get('summary') or f['finding']) + ' ' + refs(f.get('evidence'))

    def risk_detail(f):
        # Structured consequences stay in the full finding. The main risk table
        # uses a short source-led statement, without clipping mid-sentence.
        value = safe_text(f.get('summary') or f['finding'])
        if f['topic'] == 'energy':
            value = 'Certificate coverage has not been established for the relevant demise. The letting date, EPC scope and any exemption need reconciliation; a missing search result does not establish a breach.'
        elif f['id'] == 'cover-hazard-interaction':
            value = safe_text(f['finding']) + ' A modelled hazard is not evidence of physical damage.'
        elif f['id'].startswith('fire-actions'):
            sentences = re.split(r'(?<=[.!?])\s+', value)
            value = ' '.join(sentences[:2]) + ' Current action-closure evidence is outstanding.'
        return value + ' ' + refs(f.get('evidence'))

    commercial = [d for d in ds if d.get('document') and not d.get('residential_reversion')]
    principal = finance['principal']
    gates = [f for f in fs if f['materiality'] == 'decision_gate']
    records = inv['market']['records']
    external = inv['external_research']['records']
    market = inv['market']
    yield_value = ratio(rent, price)
    price_basis = report.get('assessment_price_basis') or 'Price basis unconfirmed'
    sold = str(report.get('listing_status', '')).upper() == 'SOLD'
    vacant = inv['profile'].get('vacant')
    price_label = 'Reported sale' if 'reported sale' in price_basis.lower() else 'Guide price' if 'guide' in price_basis.lower() else 'Assessment price'
    rent_label = 'Current income' if vacant else 'Lease rent' if inv.get('income_reconciled') else 'Advertised rent'
    title = 'PROPERTY SNAPSHOT / FREE' if not has_pack else 'INVESTMENT REPORT / REVIEW COPY'
    header = [p('AUCTION GEEK  /  ' + title, 'kicker'), p(report['property'], 'title'),
              p(('Retrospective sold-lot review' if sold else 'Property assessment') + '  |  ' + str(report.get('created_at', ''))[:10], 'meta')]
    metrics = [(price_label, cash(price)), (rent_label, 'Vacant' if vacant else cash(rent) + ' pa' if rent is not None else 'Not established'),
               ('Gross yield', f'{yield_value:.2f}%' if yield_value is not None else 'Not established')]
    header.append({'kind': 'metrics', 'items': metrics})
    attraction = (f'{cash(rent)} annual rent gives {yield_value:.2f}% gross at {cash(price)} before costs.'
                  if yield_value is not None else 'A dependable current income yield cannot be established.')
    if vacant:
        attraction = 'The property has no established current income. Its investment case depends on the cost and time needed to secure occupation.'
    income_note = ('Lease rents reconcile arithmetically; current collection and tenant affordability remain unverified.'
                   if inv.get('income_reconciled') else 'Advertised income is unverified against operative leases and receipts.')
    if vacant:income_note='Vacancy is reported in the particulars; no tenancy income has been assumed.'
    market_note = ('Achieved comparable evidence exists, but a supported adjustment to the subject is still required.'
                   if market['price_support'] == 'evidence_requires_adjustment' else
                   'The available market evidence does not establish that this price is fair value.')
    if price is None:market_note='The purchase price has not been established; a price-based assessment is unavailable.'
    verdict = ('Investment case on hold' if gates else 'Conditional investment case; verification outstanding') if has_pack else 'Public evidence only; full assessment unavailable'
    executive = attraction + ' ' + income_note + ' ' + market_note
    conclusion = ('Do not underwrite the headline yield as dependable income while the decision-blocking matters remain unresolved. '
                  if gates else 'The return depends on supported income, costs and the operative rights being acquired. ') + market_note

    # The public-only pathway is deliberately a concise free product.
    if not has_pack:
        page1 = header + [h('What the evidence tells you'), p(executive)]
        heritage = next((r for r in external if r['kind'] == 'heritage_designation'), None)
        if heritage:
            page1 += [p(heritage['source']['title'] + ' ' + ref_record(heritage), 'small')]
        epcs = [r for r in external if r['kind'] == 'epc_certificate']
        page1.append(h('Before underwriting a new letting' if vacant else 'One point to investigate before relying on the yield'))
        insights = public_insights(report)
        if insights:
            for insight in insights[:2]:
                page1 += [p(insight['title'], 'callout'), p(insight['finding'] + ' ' + insight['consequence'] + ' ' + refs([dict(insight['source'], document=insight['source']['title'])] + [dict(s, document=s['title']) for s in insight.get('additional_sources', [])]), 'small')]
        elif epcs:
            r = epcs[0]
            page1.append(p('The public EPC candidate relates to ' + str(r.get('address') or r.get('subject')) +
                           ', rating ' + str(r.get('rating')) + '. Its extent has not been reconciled to the investment. A certificate for one unit cannot clear the whole property. ' + ref_record(r)))
        else:
            page1.append(p('Confirm the current occupation and operative income. A listing rent or potential rent does not establish the cash a buyer will collect.'))
        page1 += [h('What a full assessment still needs'), p('Title and plans; building condition; a costed works and reletting plan; insurance, compliance and holding costs; and independent rental and sale evidence.' if vacant else 'Operative leases and variations; current rent ledger; title and plans; repair/recovery obligations; insurance and compliance evidence; and independent commercial comparables.'),
                  p('This is a free Property Snapshot. No legal pack was analysed. Missing evidence is not a finding of a breach.', 'callout')]
        public_rows = []
        public_market = [r for r in records if r['kind'] in ('subject_asking_sale','subject_asking_rent','rental_comparable','sale_comparable')]
        public_market.sort(key=lambda r: 0 if r.get('price_basis')=='achieved' else {'rental_comparable':1,'subject_asking_rent':2,'subject_asking_sale':3}.get(r['kind'],4))
        for r in public_market[:3]:
            if r['kind'] in ('subject_asking_sale', 'subject_asking_rent', 'rental_comparable', 'sale_comparable'):
                value = r.get('price') if r.get('price') is not None else r.get('rent')
                public_rows.append([r['source']['title'], cash(value) + (' pa' if r.get('price') is None and r.get('rent') is not None else ''),
                                    (r.get('price_basis') or r.get('rent_basis') or 'Unclassified') + '; captured ' + str(r['source'].get('observed_at') or 'date unavailable')[:10] + ' ' + ref_record(r)])
        result = next((r for r in external if r['kind'] == 'subject_sale_result'), None)
        price_row = [price_label, cash(price), price_basis + (' ' + ref_record(result) if result else '')]
        page2 = [h('Price and market context'), table(['Evidence', 'Amount', 'Basis / source'], [price_row] + public_rows, [.40, .16, .44]),
                 p('Subject marketing asks and neighbouring asking figures are context only. They do not establish achieved value, sustainable rent or a reletting period.', 'small')]
        if report.get('guide'):
            page2.append(p('Earlier auction guide: ' + cash(report['guide']) + (' - ' + cash(report['guide_upper']) if report.get('guide_upper') and report['guide_upper'] != report['guide'] else '') + '. The assessment uses the separately labelled price above.', 'small'))
        page2 += [p('Yield is advertised rent divided by the stated price. Fees, tax, works and holding costs are additional. This snapshot does not establish net yield.', 'small'),
                  {'kind': 'sources', 'rows': list(references.values())}]
        return {'pages': [{'title': 'Free Property Snapshot', 'blocks': page1 + page2}],
                'appendix_pages': [], 'financial_view': finance, 'references': list(references.values()),
                'conclusion': conclusion, 'executive_assessment': executive, 'status': 'Free Property Snapshot - public evidence',
                'appendix_findings': [], 'selection_note': 'Public evidence only.', 'product_outcome': 'free_snapshot'}

    if not inv.get('income_reconciled') and market['price_support']=='inconclusive' and market['erv_support']=='inconclusive':
        from acquisition_quality import evidence_sufficiency
        outcome=evidence_sufficiency(report)
        header[0]=p('AUCTION GEEK / EVIDENCE CHECK / NO CHARGE','kicker')
        blocks=header+[h('A full investment assessment is not yet supportable'),
            p('The supplied pack has been processed, but its operative interests and income have not been sufficiently resolved. This is an incomplete evidence result, not a £19 Investment Report.'),
            p(executive,'small'),h('What prevents delivery')]
        blocks += [p('Independent commercial evidence and source-grounded review remain incomplete. No price or rent is inferred to fill the gaps.','small')]
        if gates:
            blocks += [table(['Priority issue','Consequence'],[[f['title'],f['consequence']+' '+refs(f.get('evidence'))] for f in gates[:3]],[.32,.68])]
        if commercial:
            blocks += [h('Lease evidence recovered — current effect unresolved'),
                table(['Source / interest','Rent in document','Term / break'],[[d['label']+' '+refs(d.get('evidence')),cash(d.get('annual_rent')),safe_text(lease_terms(d))] for d in commercial],[.28,.18,.54]),
                p('These are document-level observations, not a verified schedule of separate current lettings. Do not add them to the advertised income.','small')]
        for f in fs:
            if f not in gates and f.get('materiality') not in ('information','routine') and 'break limits income' not in f['title'].lower():
                blocks += [h(f['title']),p(text(f),'small')]
        blocks += [h('What is needed next'),p('Resolve the operative leases, variations, plans and rent ledger, then complete independent commercial research and a source-grounded review. No full-report purchase or report-credit redemption should be requested for this result.','small'),
            {'kind':'sources','rows':list(references.values())}]
        return {'pages':[{'title':'Incomplete evidence result','blocks':blocks}], 'appendix_pages':[],
            'financial_view':finance,'references':list(references.values()),'conclusion':conclusion,
            'executive_assessment':executive,'status':'Incomplete evidence — no charge',
            'appendix_findings':fs,'selection_note':'Source findings retained for private review; not approved as a paid product.',
            'product_outcome':'insufficient_evidence'}

    page1 = header + [h(verdict), p(executive)]
    heritage = next((r for r in external if r['kind'] == 'heritage_designation'), None)
    if heritage:
        page1.append(p(heritage['source']['title'] + ' ' + ref_record(heritage), 'small'))
    elif inv['profile'].get('listed'):
        page1.append(p('Listed status identified in the property context; designation and extent require source verification.', 'small'))
    if principal:
        share = ratio(principal['annual_rent'], rent)
        page1.append(p(f"The principal letting supplies {share:.1f}% of rent. A full year without it leaves {cash(rent-principal['annual_rent'])} before any costs.", 'callout'))
    priority_rows = []
    for f in gates[:3]:
        priority_rows.append([f['title'], f['consequence'] + ' ' + refs(f.get('evidence'))])
    if priority_rows:
        page1 += [h('What prevents a dependable assessment'), table(['Issue', 'Investment consequence'], priority_rows, [.30, .70])]
    page1 += [h('The interest and the price'), p(str(report.get('tenure') or 'Tenure unconfirmed') + ' interest. ' +
               (str(len(commercial)) + ' reconciled commercial lettings; ' + str(sum(bool(d.get('residential_reversion')) for d in ds)) + ' residential long-lease interests.' if inv.get('income_reconciled') else 'The operative tenancy structure remains unresolved; lease documents must not be counted as separate current lettings.'), 'small')]
    history = [[price_label, cash(price), price_basis]]
    if report.get('guide'):
        history.append(['Earlier guide', cash(report['guide']) + (' - ' + cash(report['guide_upper']) if report.get('guide_upper') and report['guide_upper'] != report['guide'] else ''), 'Auction marketing; not an achieved transaction'])
    for r in external:
        if r['kind'] == 'subject_sale_result':
            history[0][2] += ' ' + ref_record(r)
    page1.append(table(['Price event', 'Amount', 'Meaning'], history, [.23, .25, .52]))
    page1.append(p('Review copy. Production quality and full source-review acceptance remain outstanding. ' + ('The source reports a sale; completion and subsequent availability are unverified.' if sold else ''), 'caption'))

    page2 = [h('Income: concentration and the next lease events')]
    if inv.get('income_reconciled'):
        rows = [[d['label'], d['annual_rent'], f"{ratio(d['annual_rent'],rent):.1f}%"] for d in ds if d.get('annual_rent') is not None]
        page2 += [chart('Share of contractual rent', 'income', rows), p(income_note, 'small')]
        shown.update({'income-concentration', 'income-reconciliation'})
    events, unresolved = lease_events(ds)
    if events:
        page2.append(chart('Lease-event timeline', 'timeline', events))
        page2.append(p('Breaks are conditional rights, not forecasts of tenant departure. ' + refs([e for x in events for e in x['evidence']]), 'caption'))
    for event in unresolved:
        page2.append(p(event['label'] + ': ' + event['reason'] + ' ' + refs(event['evidence']), 'small'))
    rows = [[d['label'] + ' ' + refs(d.get('evidence')), cash(d.get('annual_rent')), lease_terms(d)] for d in commercial]
    page2.append(table(['Commercial letting', 'Rent pa', 'Operative term / break'], rows, [.27, .13, .60]))
    reversions = [d for d in ds if d.get('residential_reversion')]
    if reversions:
        page2.append(p(f"{len(reversions)} residential long-lease interests contribute {cash(sum(d.get('annual_rent') or 0 for d in reversions))} pa. They do not provide vacant-possession flats to sell or residential market rent. " + refs([e for d in reversions for e in d.get('evidence', [])]), 'small'))
        shown.add('reversion-economics')
    page2.append(p('Collection, concessions, tenant affordability and the sufficiency of security still need evidence. A trading name does not establish covenant strength.', 'small'))

    page3 = [h('Material risks and who funds the building')]
    risk_rows = []
    selected = [f for f in fs if f['materiality'] == 'decision_gate']
    selected += [f for f in fs if f['id'].startswith(('asbestos-sample', 'fire-actions'))]
    for f in selected:
        risk_rows.append([f['title'], risk_detail(f), f['resolution']])
        shown.add(f['id'])
    page3.append(table(['Issue', 'Evidence and consequence', 'Resolve before relying'], risk_rows, [.18, .48, .34]))
    repair_rows = []
    for lease in report.get('lease_details', []):
        if not lease.get('repairs'):
            continue
        label = next((d['label'] for d in ds if d.get('document') == lease['document']), lease['document'])
        repair_rows.append([label, repair_summary(lease) + ' ' + refs([e for r in lease['repairs'] for e in r.get('evidence', [])])])
    if repair_rows:
        page3 += [h('Repair duty and recovery are separate'), table(['Interest', 'Allocation recovered from source'], repair_rows, [.27, .73])]
        shown.add('repair-recovery')
    page3.append(p('Landlords may need to fund works before recovering tenant shares. A recovery clause does not establish full recovery, collectability or an adequate reserve.', 'small'))
    if inv['profile'].get('listed'):
        page3.append(p('Repair budgeting must reflect the recorded listed status. No priced specification or current survey budget has been established.', 'small'))

    page4 = [h('Commercial evidence: rent, price and exit')]
    market_rows, chart_rows = [], []
    for r in records:
        if r['kind'] not in ('subject_asking_sale', 'subject_asking_rent', 'rental_comparable', 'sale_comparable'):
            continue
        value = r.get('price') if r.get('price') is not None else r.get('rent')
        basis = r.get('price_basis') or r.get('rent_basis') or 'Unclassified'
        market_rows.append([r['source']['title'], cash(value) + (' pa' if r.get('price') is None and r.get('rent') is not None else '') + ' / ' + basis,
                            market_commentary(r) + ' Captured ' + str(r['source'].get('observed_at') or 'date unavailable')[:10] + ' ' + ref_record(r)])
        if r.get('rent') and r.get('area_sqft') and r.get('rent_basis') in ('asking', 'achieved'):
            chart_rows.append([r.get('address') or r['source']['title'], r['rent']/r['area_sqft'], basis + ' / ' + str(r['area_sqft']) + ' sq ft'])
    achieved = [r for r in records if r['kind']=='sale_comparable' and r.get('price_basis')=='achieved'
                and r.get('comparable') is True and r.get('price') and r.get('rent') is not None]
    if achieved and yield_value is not None:
        yield_rows = [['Subject / '+price_label.lower(), yield_value]]
        yield_rows += [[r.get('address') or r['source']['title'], ratio(r['rent'], r['price'])] for r in achieved]
        page4 += [chart('Headline gross yields: subject and achieved sales', 'yield', yield_rows),
                  p('Rent divided by the stated price. Before fees, incentives, voids and costs; not net initial yields or a valuation range.', 'caption')]
    elif len(chart_rows) > 1:
        page4 += [chart('Rental evidence per quoted square foot', 'comparables', chart_rows, unit='£ / sq ft pa'),
                  p('Unadjusted observations. Areas, basement content, condition, incentives and lease terms differ. Subject marketing is not independent rental evidence.', 'caption')]
    page4.append(table(['Evidence', 'Amount / basis', 'Interpretation'], market_rows, [.28, .19, .53]))
    page4 += [h('What this means commercially'), p(market_note + ' ' + ('Achieved lettings need adjustment before supporting an ERV.' if market['erv_support'] == 'evidence_requires_adjustment' else 'An ERV and reliable reletting period remain unestablished.'), 'small')]
    for r in achieved[:2]:
        if yield_value is not None:
            spread = yield_value-ratio(r['rent'],r['price'])
            page4.append(p(f"The subject headline yield is {abs(spread):.2f} percentage points {'above' if spread>=0 else 'below'} {r.get('address') or r['source']['title']}. That spread must be judged against differences in lease security, pitch, condition, incentives and retained liabilities; it is not a measured discount to fair value. " + ref_record(r), 'small'))
        terms = [t for t in external if t['kind']=='comparable_terms' and ((t.get('comparison_id') and t.get('comparison_id')==r.get('id')) or (t.get('comparison_source_id') and t.get('comparison_source_id')==r.get('source_id')))
                 and compact(t.get('subject')).casefold()==compact(r.get('address')).casefold()]
        for t in terms:
            qualifiers=[]
            concession=re.search(r'rent free period until\s+([A-Za-z]+\s+20\d{2})', t['quote'], re.I)
            if concession:qualifiers.append('rent-free period until '+concession[1])
            if re.search(r'tenant break option in the fifth year',t['quote'],re.I):qualifiers.append('a fifth-year tenant break')
            if qualifiers:page4.append(p('Comparable qualifications: the particulars disclose '+ ' and '.join(qualifiers)+'. Headline reserved rent is not proof of rent collected at the sale. '+ref_record(t),'small'))
    if principal and any(r['kind']=='subject_asking_rent' and r.get('area_sqft') for r in records) and any(r['kind']=='rental_comparable' and r.get('area_sqft') for r in records):
        page4.append(p('A neighbouring asking rent per square foot does not establish that the principal letting is under-rented. Assess usable trading area and secondary space separately before underwriting replacement income.', 'small'))
    if inv['profile'].get('long_lease_reversions'):
        page4.append(p('Exit value depends on the income and rights actually owned. Sold-off flats cannot be priced as vacant residential accommodation; retained building liabilities may survive even if their ground rents are small.', 'small'))
    context = [r for r in records if r['kind'] in ('planning_context', 'occupation_history', 'marketing_history')]
    for r in context[:1]:
        page4.append(p('Local context: ' + (r.get('description') or r['quote']) + ' ' + ref_record(r), 'small'))

    page5 = [h('Cash required and the cost of losing income')]
    cost_rows = [['Assessment price', cash(price), price_basis]]
    for c in report.get('costs', []):
        cost_rows.append([c['label'], cash(c['amount']), c.get('basis', '') + ' ' + refs(c.get('evidence'))])
    if finance['illustrative_tax']:
        tax = finance['illustrative_tax']
        cost_rows.append(['Illustrative transaction tax', cash(tax['amount']), 'Price-only non-residential/mixed-use SDLT; assumptions below. ' + refs([tax['source']])])
    if finance['capital_basis']:
        cost_rows.append(['Quantified acquisition subtotal', cash(finance['capital_basis']), 'Partial cash requirement; further costs remain unquantified'])
    page5.append(table(['Cash item', 'Amount', 'Evidence / limitation'], cost_rows, [.36, .15, .49]))
    if finance['illustrative_tax']:
        page5.append(p(finance['illustrative_tax']['basis'], 'caption'))
    if finance['rent_loss_cases']:
        page5.append(chart('Annual rent remaining after principal-tenant loss', 'downside', [[s['label'], s['rent_remaining']] for s in finance['rent_loss_cases']]))
        page5.append(p('Assumes other rents are collected unchanged. These are income amounts before all costs, not net cash forecasts. Vacancy rates, insurance, works, incentives and reletting fees are additional.', 'caption'))
    if finance['historical_costs']:
        for cost in finance['historical_costs']:
            page5.append(p(f"Documented cost context: {cash(cost['amount'])} building expenditure for {cost['period']}. {cost['basis']} " + refs(cost['evidence']), 'small'))
    reserve = find('reserve-cash-reconciliation')
    if reserve:
        page5.append(p(text(reserve) + ' ' + reserve['consequence'], 'small'))
        shown.add('reserve-cash-reconciliation')
    if finance['cost_capacity']:
        c = next(x for x in finance['cost_capacity'] if x['hurdle_pct'] == 10)
        page5.append(p(f"Cost discipline: a purely illustrative 10% annual cash return on the {cash(finance['capital_basis'])} partial acquisition subtotal leaves {cash(c['annual_cost_capacity'])} pa for all income loss and running costs. Further acquisition costs reduce that ceiling; finance, tax and capital work are additional. This is a hurdle calculation, not an estimated net yield.", 'small'))
    page5 += [p('Still unquantified: ' + '; '.join(finance['unknown_costs']) + '. No zero-cost assumption is made. The deposit is part of the price.', 'caption'),
              h('Investment conclusion'), p(conclusion, 'small')]

    remaining = [f for f in fs if f['id'] not in shown and f['materiality'] in ('decision_gate', 'price_sensitive')]
    # Put every remaining material issue in the printed appendix, with a visible
    # index in the main brief. Distinct leases retain distinct headings.
    if remaining:
        page3.append(p('Additional material checks in the appendix: ' + '; '.join(f['title'] for f in remaining) + '.', 'caption'))
    appendix = [h('Evidence appendix'), p(report.get('evidence_scope', {}).get('summary', '') +
                 f" Scope: {report.get('coverage', {}).get('pages', 0)} supplied pages. Source dates and review limits remain material.", 'small')]
    for f in remaining:
        appendix += [h(f['title']), p(text(f)), p(f['consequence'] + ' Resolve: ' + f['resolution'], 'small')]
    appendix.append({'kind': 'sources', 'rows': list(references.values())})
    return {'pages': [{'title': title, 'blocks': blocks} for title, blocks in zip(
            ['Investment assessment', 'Income and lease events', 'Risks and liabilities', 'Commercial evidence', 'Cash and downside'],
            [page1, page2, page3, page4, page5])],
            'appendix_pages': [{'title': 'Evidence appendix', 'blocks': appendix}],
            'financial_view': finance, 'references': list(references.values()), 'conclusion': conclusion,
            'executive_assessment': executive, 'status': 'Investment report - review copy; paid release closed',
            'appendix_findings': fs, 'selection_note': 'Source excerpts are retained separately from interpreted customer findings.',
            'product_outcome': 'review_required'}
