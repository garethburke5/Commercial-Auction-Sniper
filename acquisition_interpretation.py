"""Stage B: connect verified findings before Stage C writes the customer brief.

Rules operate on evidence types, values and relationships, never property names.
Every interpretation keeps its inputs; missing evidence never becomes a fact.
This bounded analysis complements, and cannot certify, the open evidence review.
"""
from __future__ import annotations
import re
from acquisition_financials import financial_view
from acquisition_editorial import customer_findings, exact_date, lease_events
from acquisition_underwriting import underwriting_view, presentation_priority


def money(v):
    if v is None: return 'an unconfirmed amount'
    return f'£{v:,.0f}' if float(v).is_integer() else f'£{v:,.2f}'


def dated(value):
    d=exact_date(value)
    return d.strftime('%d %B %Y').lstrip('0') if d else None


def sentence(text):
    text=re.sub(r'\s+',' ',str(text or '')).strip()
    return text if not text or text.endswith(('.', '!', '?')) else text+'.'


def supported_terms(record, external):
    """Never borrow tenancy terms from a different comparable."""
    address=' '.join(str(record.get('address','')).lower().split())
    return [r for r in external if r.get('kind')=='comparable_terms' and address
            and ' '.join(str(r.get('subject','')).lower().split())==address
            and ((r.get('comparison_id') and r['comparison_id']==record.get('id'))
                 or (r.get('comparison_source_id') and r['comparison_source_id']==record.get('source_id')))]


def source_evidence(record):
    return [dict(record['source'],document=record['source'].get('title'))] if record.get('source') else []


def interpret(report):
    from acquisition_public_terms import published_terms
    from acquisition_unit_schedule import income_schedule
    public = published_terms(report)
    inv=report['investigation']; finance=financial_view(report); underwriting=underwriting_view(report)
    findings=customer_findings(report); ds=inv.get('demises',[])
    profile=inv.get('profile',{}); external=inv.get('external_research',{}).get('records',[])
    cards=[]; covered=set(); unedited=[]
    def add(key,title,body,finds=(),evidence=(),kind='finding'):
        finds=list(finds); ev=list(evidence)
        for f in finds:
            covered.add(f['id']);ev.extend(f.get('evidence',[]))
        cards.append({'id':key,'title':title,'body':sentence(body),'finding_ids':[f['id'] for f in finds],
                      'evidence':ev,'kind':kind,
                      'priority':min((presentation_priority(f) for f in finds),default=50)})
    def matching(prefix): return [f for f in findings if f['id'].startswith(prefix)]
    principal=finance['principal']; rent=finance['rent']; price=finance['price']
    if profile.get('vacant'):
        opening='This is a purchase of an empty building, so the investment depends on finding an occupier and paying the costs of getting it ready. There is no current rental income to offset those costs.'
    elif rent is not None and price:
        label='annual lease rent' if inv.get('income_reconciled') else 'current tenant rent' if public.get('passing') == rent else 'advertised annual rent'
        opening=f"The {label} of {money(rent)} provides a gross yield of {rent/price*100:.2f}% at a {'guide price' if 'guide' in str(report.get('assessment_price_basis')).lower() else 'price'} of {money(price)}, before purchase and running costs."
    elif rent is not None:
        opening=f'The advertised annual rent is {money(rent)}. A purchase price is needed to calculate the gross rental yield.'
    else:
        opening='The available information does not establish both the purchase price and current annual rent, so it cannot yet show the return a buyer could receive.'
    ownership=f"The property is {str(report['tenure']).lower()}." if report.get('tenure') else 'The ownership interest needs confirming.'
    if public.get('upper_parts_sold') and not inv.get('income_reconciled'):
        ownership+=' The upper parts have already been sold on long leases; their residential letting income is not included in this investment.'
    residential=[d for d in ds if d.get('residential_reversion')]
    commercial=[d for d in ds if d.get('document') and not d.get('residential_reversion')]
    if inv.get('income_reconciled'):
        ownership+=f" The identified income comes from {len(commercial)} commercial {'letting' if len(commercial)==1 else 'lettings'}."
        ownership+=' '+ '; '.join(f"{d['label']} produces {money(d['annual_rent'])} a year" for d in commercial)+'.'
    if residential:
        ownership+=f" The {len(residential)} {'flat has' if len(residential)==1 else 'flats have'} already been sold on long leases."
        if income_schedule(report)['reconciled']:
            ownership+=f" A buyer would receive {money(sum(d['annual_rent'] for d in residential))} a year in ground rent, rather than the market rents from letting the flats."
        else:
            ownership+=' The ground rents need confirming separately; the buyer does not receive the flats’ residential letting income.'
    if profile.get('listed'):
        heritage=next((r for r in external if r.get('kind')=='heritage_designation'),None)
        grade=re.search(r'Grade:\s*(II\*?|I)\b',heritage.get('quote','')) if heritage else None
        ownership+=' The building is '+('Grade '+grade[1]+' listed' if grade else 'listed')+', so proposed alterations and repair methods may need specialist advice and consent.'
    repairs=matching('repair-recovery');energy=[f for f in findings if f.get('topic')=='energy' and f.get('materiality')=='decision_gate']
    insurance=matching('cover-hazard');title=matching('title-exclusion')
    combined=''
    if principal and rent:
        share=principal['annual_rent']/rent*100
        b=next((b for b in principal.get('breaks',[]) if not b.get('uncertain') and dated(b.get('date_raw'))),None)
        combined=f"{principal['label']} provides {share:.1f}% of the rent."
        if b:combined+=f" Its tenant can end the lease on {dated(b['date_raw'])}, if the lease conditions are met."
        combined+=(f" A full year without this tenant would leave {money(rent-principal['annual_rent'])} in rent from the other interests, before costs." if rent>principal['annual_rent'] else ' A full year without this tenant would leave no rental income from the identified lettings.')
        if repairs:
            combined+=' The landlord could therefore lose most of the income while still having to arrange and fund building repairs.' if share>50 else 'Building repair obligations could continue while that income is missing.'
        if profile.get('listed') and repairs:combined+=' The listed status makes it especially important to price the right repairs before committing.'
        inputs=matching('income-concentration')+repairs
        add('income-building-interaction','When income falls, the building still needs funding',combined,inputs,principal.get('evidence',[]),kind='interaction')
    elif not profile.get('vacant'):
        combined='The rent figures have not yet been matched to all the current leases and later changes. The advertised total should not be treated as confirmed income.'
    for f in title:
        add('ownership-extent','Title boundaries and access',
            'The register excludes the ground floor within a defined part of the title plan. This is a description of the ownership boundary, not by itself a title defect. Compare that area with the lease plans and access rights; it matters commercially if rental space, access or repair responsibilities are affected.',[f])
    for f in energy:
        unit=next((d for d in ds if d.get('id') and f.get('id','').endswith('-'+d['id'])),None)
        if unit is None:
            unit=next((d for d in ds if any(e.get('document')==d.get('document') for e in f.get('evidence',[]))),None)
        name=unit['label'] if unit else 'the relevant commercial space'
        state=f.get('id','')
        if state.startswith('epc-substandard') and unit and unit.get('epc'):
            body=f"The Energy Performance Certificate (EPC) matched to {name} records a rating of {unit['epc']['rating']}. The letting position needs assessment against the applicable requirements and any valid exemption."
        elif state.startswith('epc-expired'):
            body=f'The energy certificate identified for {name} has expired. A current Energy Performance Certificate (EPC), or evidence that one is not required, is needed before relying on the letting position.'
        else:
            body=f'We have not established a current Energy Performance Certificate (EPC) covering {name}. A failed register search does not prove that the letting is unlawful.'
        if profile.get('listed'):body+=' Listed status alone does not settle whether a certificate or energy improvements are required.'
        if not (unit and unit.get('epc')):
            body+=' The seller should supply the certificate or explain the legal basis for not needing one.'
        body+=' Any required improvements could affect the purchase budget and the time needed to relet the unit.'
        add(f['id'],'Energy requirements for '+name,body,[f])
    for f in insurance:
        if 'excludes subsidence' in (f.get('finding','')+' '+f.get('summary','')).lower():
            body='The insurance certificate expressly excludes subsidence. That leaves a potentially serious gap if the building suffers that type of damage. The environmental search is a warning about possible hazards, not evidence that the building is damaged. A buyer needs an insurance quotation that addresses the exclusion, alongside advice on the building’s condition.'
            add(f['id'],'Check the insurance gap before taking ownership',body,[f])
    asbestos=matching('asbestos-sample');fire=matching('fire-actions')
    for f in fire:
        body=sentence(f.get('finding') or f.get('summary'))+' '
        body+='Completion records are needed to establish which actions, if any, remain outstanding. Any remaining work needs costing and responsibility allocating before the buyer can settle the purchase budget.'
        add('fire-safety-'+f['id'],'Fire-safety work and completion records',body,[f])
    for f in asbestos:
        reviewed=f.get('reviewed_interpretation') or {}
        body=sentence(f.get('finding') or f.get('summary'))+' '
        if reviewed:
            body+=' '.join(sentence(reviewed.get(k,'')) for k in ('location','investment_significance'))+' '
        body+='The survey describes the material at its inspection date. Its location, current condition and management recommendations determine the practical implications.'
        add('asbestos-'+f['id'],'Historical asbestos survey',body,[f])
    if repairs:
        clauses=' '.join(x.get('text','') for lease in report.get('lease_details',[]) for x in lease.get('repairs',[]))
        structural=bool(re.search(r'The Landlord must:.{0,180}foundations, roof.{0,100}chimneys',clauses,re.I))
        detail=('The leases expressly make the landlord responsible for the foundations, roof and chimneys. ' if structural else '')
        add('repair-allocation','Tenant contributions may not cover every repair',
            detail+'The leases include landlord responsibilities for the building and provisions for tenants to contribute. Those are different questions: the landlord may have to organise and pay for work first, then recover only the shares allowed by each lease. Empty units, disputed charges or unpaid contributions could leave a shortfall.',repairs)
    for f in matching('reserve-cash-reconciliation'):
        # Preserve the actual arithmetic, but never convert it into buyer debt.
        amounts=re.findall(r'£[\d,]+(?:\.\d{1,2})?',f.get('finding',''))
        if len(amounts)>=4:
            body=f'One flat’s reserve account shows {amounts[0]} brought forward and {amounts[1]} collected, against {amounts[2]} of work. That leaves a {amounts[3]} shortfall. The period shown on the account also needs correction. The amount is small, but the buyer needs to know which balances and unpaid charges transfer on completion.'
            add(f['id'],'Check the money held for repairs',body,[f])
    for f in matching('water-search'):
        add(f['id'],'Confirm that the water search covers this building',
            'The water search does not clearly confirm the building’s connections. Its wording refers to land or a recently built property, so the seller should confirm that the search covers the correct address and boundary. This is not evidence that the shops lack services.',[f])
    for f in matching('works-balance'):
        amount=re.search(r'£[\d,]+(?:\.\d{1,2})?',f.get('finding',''))
        if amount:add(f['id'],'Allocate the outstanding works bill',f'The conditions disclose an outstanding {amount[0]} electrical-works bill. They do not by that statement alone establish that the buyer must pay it. Ask the solicitor to confirm who is responsible; it has not been added to fixed purchase costs.',[f])
    for f in matching('cpse-asbestos'):
        add(f['id'],'The seller’s reply and survey do not agree','The seller’s enquiry reply says there is no asbestos survey or management plan, yet older asbestos reports are in the pack. Ask for a corrected reply and the current management records. Neither version establishes that the building is asbestos-free.',[f])
    for f in matching('cpse-rent-arrears'):
        add(f['id'],'Check receipts as well as the lease rent','The seller states that there are no current rent arrears. That is a dated statement, rather than a record of rent received. Obtain the payment history to check collections and any concessions; it does not settle separate repair or service-charge balances.',[f])
    for f in matching('income-unreconciled'):
        add(f['id'],'The advertised rent still needs checking','The advertised rent has not been matched to the current leases and payment history. It should be treated as a published claim until those records confirm the amount due and the money actually received.',[f])
    for f in matching('lease-extent-unresolved'):
        add(f['id'],'Match the leases to the correct premises','The documents have not been reliably matched to separate current lettings. Earlier leases and later changes may describe the same space, so their rents must not be added together.',[f])
    for f in matching('superior-interest'):
        add(f['id'],'A leasehold purchase has obligations to another owner','The interest is leasehold, so the buyer would hold the property under a lease from another owner. Its remaining term, rent, repair obligations and restrictions need checking alongside any tenancy that produces the investment income.',[f])
    for f in matching('vacancy-carry'):
        add(f['id'],'The empty period needs its own budget','An empty property produces no current rent. A buyer needs to budget for the time needed to secure an occupier, any work, insurance and other costs that continue before a letting starts.',[f])
    for f in findings:
        if 'lease expressly replaces an earlier rent' in f.get('title','').lower():
            add(f['id'],'The newer lease replaces the old rent',
                sentence(f['finding'])+' The two amounts must not be added together. This explains the lease wording; payment history and any later changes still need checking.',[f],kind='rent_substitution')
    # Findings covered by dedicated income, date and cost narratives below.
    for f in findings:
        if f['id'] in covered:continue
        if f['id'].startswith(('lease-','reversion-economics','income-reconciliation','addendum-','service-charge-table','cpse-commercial-epc','asbestos-scope-negative','contamination-')):
            if f['id'].startswith('lease-') and not any(x in f.get('title','').lower() for x in ('break','edited lease dates','ground rent','different lease rent','extent')):
                unedited.append(f)
            else: covered.add(f['id'])
        elif f['id'] not in covered and f.get('materiality') in ('decision_gate','price_sensitive'):
            if f.get('origin')=='open_review' and inv.get('open_review',{}).get('provenance_valid') and f.get('evidence'):
                add(f['id'],f['title'],' '.join(sentence(f.get(k,'')) for k in ('finding','consequence','resolution')), [f],kind='additional_review')
            else:unedited.append(f)
    market=[]
    for r in inv.get('market',{}).get('records',[]):
        if r.get('kind') not in ('sale_comparable','rental_comparable','subject_asking_sale','subject_asking_rent'):continue
        label=r.get('address') or r.get('source',{}).get('title') or 'Property reference'
        value=r.get('price') if r.get('price') is not None else r.get('rent')
        basis=r.get('price_basis') or r.get('rent_basis') or 'unconfirmed'
        if r['kind']=='subject_asking_sale':body=f'This property has also been advertised at {money(value)}. That is an asking price, not evidence that a buyer paid it. The listing date has not been verified.'
        elif r['kind']=='subject_asking_rent':body=f'The shop has been marketed at {money(value)} a year'+(f" for a quoted {r['area_sqft']:,.0f} square feet" if r.get('area_sqft') else '')+'. This is the same property, so it is not independent proof of the rent a replacement tenant would agree to pay.'
        elif basis=='achieved' and r.get('price') and r.get('rent') is not None:
            body=f"{label} sold for {money(r['price'])}. Its advertised rent of {money(r['rent'])} gives a gross yield of {r['rent']/r['price']*100:.2f}%, before costs and rent concessions."
        elif r.get('price'):
            body=f"{label} has a {basis if basis!='unconfirmed' else 'price of unconfirmed type'} price of {money(value)}. " + ('It is not an achieved sale and cannot show what buyers have actually paid.' if basis!='achieved' else 'The income and lease terms need checking before it can be compared with this investment.')
        else:
            body=f"{label} is {'advertised at' if basis=='asking' else 'reported at'} {money(value)} a year"+(f" for {r['area_sqft']:,.0f} square feet" if r.get('area_sqft') else '')+'. '+('An asking rent does not show the rent eventually agreed or any rent-free period.' if basis=='asking' else 'The area, condition and lease terms must be compared before using this figure to estimate a new rent.')
        terms=supported_terms(r,external)
        market.append({'record':r,'body':body,'terms':terms,'evidence':source_evidence(r)+[e for t in terms for e in source_evidence(t)]})
    market_summary=('We found a completed investment sale, but its different location, tenant and lease terms mean it cannot establish a fair price for this property on its own.' if any(m['record'].get('price_basis')=='achieved' for m in market) else 'The available research does not establish a fair value for the property.')
    priority=[]
    if any(f.get('materiality')=='decision_gate' for f in title):priority.append('whether the title includes the required space and access')
    if fire:priority.append('which fire-safety actions remain and what they would cost')
    if energy:priority.append('what the shop’s energy obligations require')
    if insurance:priority.append('whether suitable insurance can be obtained')
    priority_summary=('The most important unanswered questions are '+', '.join(priority[:-1])+(' and ' if len(priority)>1 else '')+priority[-1]+'.' if priority else '')
    if principal and principal.get('annual_rent') and rent:
        assessment=combined
    else:assessment=combined or 'The building’s condition, likely works and realistic letting period need to be established before a purchase budget can be assessed.'
    if profile.get('vacant'):
        conclusion='This could become an income-producing investment if an occupier can be secured at a rent that supports the total purchase and works budget. Until the likely rent, works and letting period are evidenced, a low purchase price alone would not establish value.'
    elif repairs and principal:
        conclusion='This investment needs a buyer who can manage building work and keep cash available if the main tenant leaves. The stated rent offers an attractive starting return, but it could fall sharply while repair bills continue. The case would improve with reliable rent receipts, a realistic plan for replacing the tenant and a priced schedule showing which repairs the landlord must fund. Without those, the amount left for the buyer is still unknown.'
    else:
        conclusion='The investment becomes more convincing when the current leases and receipts support the rent, the cost of ownership is clear, and other completed transactions support the price. If those checks reveal lower income or substantial unpaid work, the price would need to leave room for them.'
    if title or energy or insurance:
        conclusion+=' The ownership, letting and insurance questions need clear answers before a buyer can sensibly judge whether the price allows enough for the risks.'
    cards.sort(key=lambda c:(c['priority'],c['id']))
    return {'version':'interpretation-2','opening':opening,'ownership':ownership,'assessment':assessment,'conclusion':conclusion,'market_summary':market_summary,'priority_summary':priority_summary,
            'cards':cards,'market':market,'finance':finance,'underwriting':underwriting,'findings':findings,'covered_finding_ids':sorted(covered),
            'unedited_findings':unedited,'inputs':{'income_reconciled':bool(inv.get('income_reconciled')),'principal_document':principal.get('document') if principal else None},
            'method':'Evidence-triggered interpretation; no address-specific rules and no independent-review approval.'}
