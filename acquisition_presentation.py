"""A reusable five-section investor brief derived from the investigation.

The evidence appendix remains complete. The brief clusters related findings and
makes selection visible; page length is never used as investment approval.
"""
from __future__ import annotations
import re
from acquisition_investigation import cash, ratio


def compact(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


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
    inv = report['investigation']; ds = inv['demises']; fs = inv['findings']
    price, rent = report.get('assessment_price'), report.get('rent')
    references = {}
    def refs(evidence):
        result = []
        for e in evidence or []:
            key = (e.get('url'),e.get('document') or e.get('title'))
            if not any(key): continue
            if key not in references:
                references[key]={'id':f'S{len(references)+1:02}', 'label':e.get('document') or e.get('title') or e.get('url'),'url':e.get('url'),'pages':set()}
            item=references[key]
            if e.get('page'):item['pages'].add(str(e['page']))
            result.append(item['id'] + (':'+str(e['page']) if e.get('page') else ''))
        return '['+', '.join(dict.fromkeys(result))+']' if result else ''
    def ref_record(r):return refs([{'document':r['source']['title'],'url':r['source']['url']}])
    def p(text,style='body'):return {'kind':'p','text':text,'style':style}
    def h(text):return {'kind':'h','text':text}
    def table(headers,rows,widths):return {'kind':'table','headers':headers,'rows':rows,'widths':widths}
    def by_id(key):return next((f for f in fs if f['id']==key),None)
    def finding_text(f):return compact(f.get('summary') or f['finding'])+' '+refs(f.get('evidence'))
    commercial=[d for d in ds if not d['residential_reversion']]
    principal=max(commercial,key=lambda d:d.get('annual_rent') or 0) if commercial else None
    gates=[f for f in fs if f['materiality']=='decision_gate']
    fees=sum(c['amount'] for c in report.get('costs',[]))
    yield_value=ratio(rent,price)
    sold=str(report.get('listing_status','')).upper()=='SOLD'
    summary=(f"{report.get('tenure') or 'Tenure unconfirmed'} interest with {len(commercial)} identified commercial letting{'s' if len(commercial)!=1 else ''}" +
             (f" and {len(ds)-len(commercial)} residential long-lease reversions" if len(ds)>len(commercial) else '')+'.')
    if not inv['income_reconciled'] and len(ds)>1:
        summary=f"{report.get('tenure') or 'Tenure unconfirmed'} interest. {len(ds)} lease records require reconciliation; they do not establish the number of current lettings."
    if inv['profile']['listed']:summary='Listed building. '+summary
    if inv['profile']['vacant']:summary='Vacant '+str(report.get('tenure') or '').lower()+' commercial interest. Value depends on lettability, permitted use and the cost of bringing it into occupation.'
    attraction=(f"The stated rent produces {yield_value:.2f}% gross at {cash(price)} before costs." if yield_value is not None else 'A dependable current income yield has not been established.')
    concentration=by_id('income-concentration')
    market=inv['market']
    price_assessment=('Comparable achieved sales are available, but their differences require adjustment before treating the price as supported.'
                      if market['price_support']=='evidence_requires_adjustment' else
                      'The price remains inconclusive against market value: comparable achieved sales have not been established.')
    income_assessment=('Lease rents reconcile to the advertised total; current collection and tenant affordability remain unverified.'
                       if inv['income_reconciled'] else
                       'The advertised rent has not been reconciled to a dependable current lease schedule.')
    if inv['profile']['vacant']:
        income_assessment='There is no current contracted income; the return depends on the cost and time needed to secure occupation.'
    priorities='; '.join(f['title'].rstrip('.') for f in gates[:3])
    executive=attraction+' '+income_assessment
    if concentration and principal:
        executive+=f" The principal letting supplies {ratio(principal['annual_rent'],rent):.1f}% of income."
    if priorities:executive+=' Decision priorities: '+priorities+'.'
    executive+=' '+price_assessment
    conclusion=attraction+' '
    if inv['scenarios'] and principal:
        downside=next((x for x in inv['scenarios'] if x['label']=='Full-year void: '+principal['label']),None)
        if downside:
            conclusion+=f"A year without the principal rent reduces income to {cash(downside['rent'])} ({downside['yield']:.2f}% gross), before holding costs. "
    if gates:
        conclusion+='An acquisition case requires satisfactory evidence on '+', '.join(dict.fromkeys(f['topic'] for f in gates))+' and a funded allowance for liabilities that cannot be recovered. '
    elif inv['profile']['vacant']:
        conclusion+='The acquisition case depends on a costed route to occupation and substantiated demand. '
    else:
        conclusion+='The income case depends on operative lease terms, current collection and recoverable landlord expenditure. '
    conclusion+=price_assessment
    page1=[p('AUCTION SNIPER  /  ACQUISITION INTELLIGENCE','kicker'),
           p(report['property'],'title'),p(('Sold investment review' if sold else 'Acquisition review')+'  |  Evidence checked '+str(report.get('created_at',''))[:10],'meta')]
    media=report.get('report_media') or {}
    if media.get('photo_path'):page1.extend([{'kind':'photo','path':media['photo_path'],'url':media.get('photo_url')},p(media.get('photo_credit',''),'caption')])
    metrics=[('Reported sale' if 'reported sale' in report.get('assessment_price_basis','').lower() else 'Price basis',cash(price)),('Reserved rent',cash(rent)+' pa' if rent is not None else 'Not established'),('Gross yield',f'{yield_value:.2f}%' if yield_value is not None else 'Not established'),('Known fixed fees',cash(fees) if fees else 'Not established')]
    page1.extend([{'kind':'metrics','items':metrics},p(summary),h('Investment assessment'),p(executive)])
    if sold:page1.append(p('The source reports the lot sold. This is a retrospective specimen; completion and any subsequent availability have not been verified. The original guide was '+cash(report.get('guide'))+' to '+cash(report.get('guide_upper'))+'.','small'))
    result_record=next((r for r in inv['external_research']['records'] if r['kind']=='subject_sale_result'),None)
    if result_record:page1.append(p('Price/status source '+ref_record(result_record)+'. Yield = reserved rent ÷ stated price; this is not a net operating return.','small'))

    page2=[h('Income and ownership'),p('The lease schedule distinguishes contractual rent from money actually collected. Original residential lease parties are not necessarily the current ground-rent payers.','small')]
    rows=[]
    for d in ds:
        terms=lease_terms(d)
        tenant=(d.get('tenant') or 'Legal tenant not reliably recovered') if not d['residential_reversion'] else 'Long-lease interest; current payer unverified'
        rows.append([d['label']+' '+refs(d['evidence']),tenant,cash(d['annual_rent']),terms])
    page2.append(table(['Interest','Tenant or interest','Annual rent','Lease term and break'],rows,[.24,.23,.12,.41]))
    if inv['income_reconciled']:
        page2.append(p(f"The {cash(rent)} total reconciles arithmetically across the identified leases. Seller statements of no arrears are not a current audited collection record."))
        page2.append({'kind':'chart','chart':'income','title':'Where the contractual income comes from','rows':[(d['label'],d['annual_rent']) for d in ds]})
    else:page2.append(p('Current income remains unreconciled. Do not add historic, draft or replacement leases together.','callout'))
    page2.extend([h('Income security'),p(finding_text(concentration)+' '+concentration['consequence'] if concentration else 'Reconcile the operative lease, variations, rent concessions and current collection before underwriting income.')])
    lease_security=[l.get('security',{}) for l in report.get('lease_details',[]) if l.get('interest')!='Residential long lease']
    page2.append(p('The legal tenant named in each lease is the covenant being acquired. Trading names and public business presence do not demonstrate ability to pay; verified accounts, guarantees and current rent/deposit evidence have not been established.','small'))
    reversion=by_id('reversion-economics')
    if reversion:page2.extend([h('What the flats add'),p(reversion['consequence']+' '+refs(reversion['evidence']))])

    page3=[h('Risks that change the investment decision')]
    energy=[f for f in fs if f['topic']=='energy']
    if energy:
        page3.extend([h('Energy compliance and reletting'),p(finding_text(energy[0])),p(energy[0]['consequence'])])
        page3.append(p('Required evidence: '+energy[0]['resolution'],'small'))
    for d in ds:
        epc=d.get('epc')
        if epc:
            score=' ('+str(epc['score'])+')' if epc.get('score') is not None else ''
            provenance='official register' if epc['source'].get('url') else 'supplied certificate'
            page3.append(p(f"{d['label']}: {provenance} EPC {epc.get('rating')}{score}, valid to {epc.get('valid_until')}; assessment area {epc.get('floor_area_sqm')} m². {epc['scope_note']} "+refs([epc['source']]),'small'))
    important=[]
    insurance=by_id('cover-hazard-interaction')
    if insurance:important.append(['Decision: insurance',insurance['finding']+' '+insurance['consequence'],insurance['resolution']+' '+refs(insurance['evidence'])])
    title=by_id('title-exclusion')
    if title:important.append(['Decision: legal extent',title['finding']+' '+title['consequence'],title['resolution']+' '+refs(title['evidence'])])
    condition=[f for f in fs if re.search('^(fire-actions|asbestos-sample|service-charge-table)',f['id'])]
    if condition:
        important.append(['Cost exposure: building', ' '.join(f['finding'] for f in condition), 'Obtain current fire-action closure, asbestos management and a survey/repair budget. Test each cost against lease recovery rights; no works allowance is established. '+refs([e for f in condition for e in f['evidence']])])
    for f in gates:
        if f['topic'] not in ('energy','insurance') and f['id']!='title-exclusion':important.append([f['title'],f['finding']+' '+f['consequence'],f['resolution']+' '+refs(f['evidence'])])
    for f in fs:
        if f.get('origin')=='open_review' and f['materiality']=='price_sensitive':
            important.append([f['title'],f['finding']+' '+f['consequence'],f['resolution']+' '+refs(f['evidence'])])
    page3.append(table(['Priority issue','Investment consequence','Evidence needed'],important,[.18,.45,.37]))
    page3.append(p('The environmental model is not proof of physical damage. Missing certificates and unsuccessful public searches do not establish a legal breach. No probability, remedial cost or lender decision is invented.','small'))

    page4=[h('Market evidence and property history')]
    records=inv['market']['records']; rows=[]
    for r in records:
        if r['kind'] in ('subject_asking_sale','subject_asking_rent','rental_comparable','sale_comparable'):
            value=cash(r.get('price') if r.get('price') is not None else r.get('rent'))+(' pa' if r.get('rent') is not None else '')
            rows.append([r['source']['title'],value+' / '+(r.get('price_basis') or r.get('rent_basis') or 'Unclassified'),r.get('description') or 'Comparability requires review',ref_record(r)])
    page4.append(table(['Evidence','Quoted amount','What it can establish','Ref'],rows,[.25,.18,.48,.09]))
    page4.extend(p(t) for t in inv['market']['comments'])
    rentals=[r for r in records if r.get('area_sqft') and r.get('rent') and r.get('rent_basis')=='asking']
    if len(rentals)>1:
        page4.append(p('Quoting rents per total floor area range from '+cash(min(r['rent']/r['area_sqft'] for r in rentals))+' to '+cash(max(r['rent']/r['area_sqft'] for r in rentals))+' per sq ft. Basement weighting, unit size, frontage, condition and incentives differ, so these are not like-for-like rental valuations.','small'))
    context=[r for r in records if r['kind'] in ('planning_context','occupation_history','marketing_history')]
    if context:page4.append(h('Local change and history'))
    for r in context:page4.append(p((r.get('description') or r['quote'])+' '+ref_record(r)))
    market_limit=('Achieved rent comparables require adjustment for the subject unit and lease before supporting an ERV.'
                  if market['erv_support']=='evidence_requires_adjustment' else
                  'The evidence does not establish an ERV or a dependable reletting period.')
    market_limit+=' No adjusted valuation or maximum bid is established.'
    if any(r['kind']=='subject_asking_sale' for r in records):
        market_limit+=' Previous asking prices show marketing expectations, not the value a purchaser achieved.'
    if inv['profile']['development'] or inv['profile']['long_lease_reversions']:
        market_limit+=' Alternative-use value also requires control of the relevant space, possession, consents and a costed scheme.'
    page4.extend([h('Implications for price and rent'),p(market_limit)])

    page5=[h('Acquisition cash and downside')]
    costs=[[c['label'],cash(c['amount']),c.get('basis','')+' '+refs(c.get('evidence'))] for c in report.get('costs',[])]
    costs.insert(0,['Price used',cash(price),report.get('assessment_price_basis','')])
    if price:costs.append(['Price plus known fixed fees',cash(price+fees),'Before transaction tax, advisers, finance, voids and works'])
    page5.append(table(['Cash item','Amount','Basis'],costs,[.34,.16,.50]))
    for a in report.get('amendment_review',[]):
        if a['status']=='applied_limited_cost_amendment':page5.append(p('The latest addendum replaces the earlier seller-cost allocation. '+a['remaining_question']+' '+refs([a['evidence']]),'small'))
    page5.append(p('A deposit forms part of the price. Transaction tax depends on the final chargeable consideration and buyer/transaction facts; it has not been certified here. Unquantified repair recovery, compliance works and vacancy costs prevent a net-return calculation.','small'))
    scenarios=inv['scenarios']
    if scenarios:
        page5.append({'kind':'chart','chart':'downside','title':'Annual income if the principal letting is interrupted','rows':[(s['label'],s['rent']) for s in scenarios if s['label']=='Contract rent collected' or (principal and principal['label'] in s['label'])]})
        page5.append(p('Illustrative lost-rent cases, not forecasts. Other rents remain unchanged; business rates, incentives, works and reletting fees would reduce returns further. At the price used, gross yields are '+', '.join(f"{s['yield']:.2f}%" for s in scenarios if s['label']=='Contract rent collected' or (principal and principal['label'] in s['label']))+'.','small'))
    page5.append(h('Acquisition conclusion'))
    page5.append(p(conclusion,'small'))
    # Compact source key. Per-finding page anchors and full extracts remain in the
    # HTML appendix; the PDF keeps only the sources actually cited above.
    source_rows=[]
    for item in references.values():
        label=re.sub(r'(?:\.pdf)+$','',item['label'],flags=re.I)
        source_rows.append(dict(item,label=label,pages=sorted(item['pages'],key=lambda x:int(x) if x.isdigit() else 0)))
    page5.append({'kind':'sources','rows':source_rows})
    visual_note=' These pages were visually checked and their dispositions recorded.' if inv.get('visual_review_complete') and report['coverage'].get('unread_pages') else ''
    page5.append(p(f"Scope: {report['coverage'].get('pages',0)} supplied PDF pages; {report['coverage'].get('unread_pages',0)} pages without substantive machine text."+visual_note+' Full evidence and remaining checks are in the accompanying HTML. Research is not legal, tax or valuation advice.','caption'))
    return {'pages':[{'title':t,'blocks':b} for t,b in zip(['Investment snapshot','Income and ownership','Material risks','Market and history','Cash and downside'],[page1,page2,page3,page4,page5])], 'references':source_rows,'conclusion':conclusion,'executive_assessment':executive,'status':'Research specimen - quality approval withheld','appendix_findings':fs,'selection_note':'Related findings are grouped in this brief. The full investigation, including routine discrepancies and incomplete review coverage, remains available in the HTML evidence appendix.'}
