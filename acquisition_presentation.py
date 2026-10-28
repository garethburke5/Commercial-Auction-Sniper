"""Stage C: a readable investor report built from evidence-linked interpretation."""
from __future__ import annotations
import re
from pathlib import Path
from acquisition_investigation import cash, ratio
from acquisition_editorial import safe_text, lease_events
from acquisition_interpretation import interpret, money, dated, source_evidence
from acquisition_public_insights import public_insights
from acquisition_evidence_links import EvidenceReferences, public_url


def compact(value): return re.sub(r'\s+', ' ', str(value or '')).strip()


def lease_terms(unit):
    """Explain dates without reproducing clauses or guessing amended text."""
    label=unit.get('label','This letting');parts=[]
    term=unit.get('term') or {};events,_=lease_events([unit])
    end=next((x for x in events if x['label'].endswith('/ expiry')),None)
    if end:
        from datetime import date
        parts.append('The lease ends on '+date.fromisoformat(end['date']).strftime('%d %B %Y').lstrip('0')+'.')
    elif term.get('uncertain'):parts.append('The printed end date contains conflicting wording and needs confirmation from the signed lease.')
    elif unit.get('lease_date'):parts.append('The lease is dated '+str(unit['lease_date'])+'; its end date has not been reliably established.')
    else:parts.append('The lease end date has not been reliably established.')
    for b in unit.get('breaks',[]):
        when=None if b.get('uncertain') else dated(b.get('date_raw'))
        if not when:parts.append('The tenant has an early termination clause, but its date cannot be read reliably. The right also depends on meeting the lease conditions.')
        else:
            party=(b.get('party') or 'party with the break right').lower()
            parts.append(f'The {party} can end the lease early on {when}, if the conditions are met.')
        if re.search(r'six months',b.get('notice_raw',''),re.I):parts.append('At least six months’ notice is required.')
    return ' '.join(parts)


def repair_summary(lease):
    return 'The lease describes repair responsibilities and tenant contributions. The full clauses need checking to establish which costs the landlord must pay and how much can be recovered.'


def market_commentary(record):
    basis=record.get('price_basis') or record.get('rent_basis')
    return 'This is an asking figure, rather than a completed transaction.' if basis=='asking' else 'The location, accommodation, tenant and lease terms need to be compared before this figure can support a valuation.'


def make_brief(report):
    if report.get('reviewed_memorandum'):
        from acquisition_memorandum import memorandum_brief
        return memorandum_brief(report)
    from acquisition_narrative import render_narrative
    from acquisition_evidence_links import end_references
    return end_references(render_narrative(report, _make_brief(report)), report)


def _make_brief(report):
    from acquisition_public_terms import published_terms, natural_date
    from acquisition_unit_schedule import schedule_blocks
    public = published_terms(report)
    if report.get('access')=='snapshot':raise ValueError('Full report required')
    analysis=interpret(report); inv=report['investigation']; finance=analysis['finance']; ds=inv.get('demises',[])
    has_pack=bool(report.get('evidence_scope',{}).get('legal_pack_supplied',bool(report.get('documents'))))
    external=inv.get('external_research',{}).get('records',[]); profile=inv.get('profile',{})
    price,rent=finance['price'],finance['rent'];principal=finance['principal'];reference_index=EvidenceReferences(report)
    def refs(evidence,context=None):
        return reference_index.add(evidence,context)
    def p(text,style='body'):return {'kind':'p','text':safe_text(text),'style':style}
    def h(text):return {'kind':'h','text':text}
    def cite(evidence,context=None):
        rows=refs(evidence,context)
        return [{'kind':'evidence','rows':rows}] if rows else []
    def section(card):return [h(card['title']),p(card['body'])]+cite(card['evidence'],card['title'])
    def table(headers,rows,widths):return {'kind':'table','headers':headers,'rows':rows,'widths':widths}
    def chart(title,kind,rows,**kw):return dict(kind='chart',chart=kind,title=title,rows=rows,**kw)
    def card(key):return next((c for c in analysis['cards'] if c['id']==key),None)
    def record_ref(r):return source_evidence(r)
    price_basis=str(report.get('assessment_price_basis') or '')
    price_label='Reported sale price' if 'reported sale' in price_basis.lower() else 'Guide price' if 'guide' in price_basis.lower() else 'Price used'
    prior_sale=next((r for r in external if r.get('kind')=='subject_sale_status' and r.get('status')=='sold_prior' and compact(r.get('subject')).casefold()==compact(report['property']).casefold() and re.search(r'\bSold Prior\b',r.get('quote',''),re.I)),None)
    if prior_sale and price is None:price_label='Sale price'
    vacant=profile.get('vacant');yield_value=ratio(rent,price) if not vacant else None
    title='PROPERTY SNAPSHOT / FREE' if not has_pack else 'FULL INVESTMENT REPORT / REVIEW COPY'
    date_text=str(report.get('created_at',''))[:10]
    display_address=re.sub(r'\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b',lambda m:m[0].upper(),report['property'],flags=re.I)
    header=[p('AUCTION GEEK  /  '+title,'kicker'),p(display_address,'title'),p('Prepared '+date_text+('  |  Review of a reported sale' if str(report.get('listing_status','')).upper()=='SOLD' else ''),'meta')]
    metrics=[(price_label,'Not disclosed' if prior_sale and price is None else cash(price)),('Current income' if vacant else 'Annual lease rent' if inv.get('income_reconciled') else 'Current tenant rent' if public.get('passing') == rent else 'Advertised annual rent','Vacant' if vacant else cash(rent)),('Gross yield',f'{yield_value:.2f}%' if yield_value is not None else 'Not applicable' if vacant else 'Not calculable')]
    header.append({'kind':'metrics','items':metrics})
    media=report.get('report_media') or {};photo=media.get('photo_path')
    if photo and Path(photo).is_file():
        if media.get('source_url'):refs([{'document':'Property photograph and attribution','url':media['source_url']}])
        if media.get('license_url'):refs([{'document':'Photograph reuse licence','url':media['license_url']}])
    # A supplied, correctly attributed photograph is optional. Never invent one.
    def overview(text):
        if photo and Path(photo).is_file():
            return [{'kind':'hero','path':photo,'text':text,'credit':media.get('photo_credit','Property photograph; capture date unconfirmed.'),
                     'source_url':public_url(media.get('source_url')),'license_url':public_url(media.get('license_url'))}]
        return [p(text)]
    heritage=next((r for r in external if r.get('kind')=='heritage_designation'),None)
    sale=next((r for r in external if r.get('kind')=='subject_sale_result'),None)
    records=inv.get('market',{}).get('records',[])
    achieved=[r for r in records if r.get('kind')=='sale_comparable' and r.get('price_basis')=='achieved' and r.get('comparable') is True and r.get('price') and r.get('rent') is not None]
    def finish(pages,appendix,outcome,status):
        from acquisition_editorial import audit_brief
        if has_pack:
            for finding in analysis['findings']:refs(finding.get('evidence'),finding.get('title'))
        result={'pages':pages,'appendix_pages':appendix,'financial_view':finance,'references':list(reference_index.rows.values()),
                'executive_assessment':analysis['opening']+' '+analysis['assessment']+' '+analysis['market_summary'],'conclusion':analysis['conclusion'],
                'status':status,'appendix_findings':analysis['findings'] if has_pack else [],
                'selection_note':'Original source extracts are retained for checking. They are not the edited customer assessment.',
                'product_outcome':outcome,'interpretation':{k:analysis[k] for k in ('version','inputs','method','unedited_findings')}}
        result['editorial_quality']=audit_brief(result)
        return result
    # A genuinely useful public introduction; no legal-pack conclusions leak here.
    if not has_pack:
        intro=analysis['opening']+' '+analysis['ownership']
        blocks=header+overview(intro)
        if public['evidence']:blocks+=cite(public['evidence'])
        if heritage:blocks+=cite(record_ref(heritage),'Listed building status')
        if report.get('auction_date'):
            from datetime import date
            try:
                auction_day=date.fromisoformat(str(report['auction_date'])[:10]);prepared=date.fromisoformat(date_text)
                if (prepared-auction_day).days>180:blocks.append(p('These figures come from the auction on '+auction_day.strftime('%d %B %Y').lstrip('0')+'. They describe the property at that time; the present rent and lease arrangements need fresh confirmation.','small'))
            except ValueError:pass
        insights=public_insights(report)
        blocks.append(h('Property and investment potential' if vacant else 'Property and rental income'))
        if public.get('top_up') is not None:
            end=natural_date(public['uplift_date']) if public.get('uplift_date') else str(public['uplift_year'])
            detail=f"The advertised {cash(public['headline'])} includes a seller-funded top-up equivalent to {cash(public['top_up'])} a year until the tenant’s rent rises in {end}."
            if public.get('uplift_date'):detail=detail.replace('rises in '+end,'rises on '+end)
            if price:detail+=f" This produces a headline gross yield of {public['headline']/price*100:.2f}%."
            detail+=' Check the sale conditions for the amount, payment timing and protection of the seller’s contribution.'
            blocks+=[p(detail)]+cite(public['evidence']+public['lease_evidence'])
        if public.get('tenant') and (public.get('top_up') is not None or public.get('break_year') or public.get('company')):
            detail='The commercial premises are let to '+public['tenant']+'.'
            if public.get('expiry'):detail+=' The advertised lease expires on '+natural_date(public['expiry'])+'.'
            if public.get('break_year'):
                detail+=f" Earlier particulars describe a tenant break in year {public['break_term']} ({public['break_year']}). This could end the income before the lease expires; the signed lease needs to establish the exact date and conditions."
            blocks+=[p(detail)]+cite(public['evidence']+public['lease_evidence'])
        elif insights:
            for x in insights[:2]:
                blocks+=[p(x['finding']+' '+x['consequence'])]+cite([dict(x['source'],document=x['source'].get('title'))]+[dict(s,document=s.get('title')) for s in x.get('additional_sources',[])])
        elif public.get('top_up') is None:
            epc=next((r for r in external if r.get('kind')=='epc_certificate'),None)
            if epc:
                blocks+=[p('The energy certificate we found is for '+str(epc.get('address') or epc.get('subject'))+'. It does not establish the energy position for every shop in this investment. Check that each certificate covers the space actually being let; any required work could affect costs and future lettings.')]+cite(record_ref(epc))
            elif vacant:
                blocks+=[p('A buyer would need to fund the empty period and any work before rent starts. An agent’s estimate of possible rent is not the same as an agreed tenancy.')]
            else:
                blocks+=[p('The advertised rent is a starting point, rather than proof of income received. The leases and payment history are needed to check whether tenants can leave early, receive rent concessions or owe money.')]
        areas=analysis['underwriting']['accommodation']
        floors={a['label'].casefold():a for a in areas}
        for area in areas[:1]:
            if 'ground-floor shop' in floors and 'basement' in floors:
                ground,basement=floors['ground-floor shop'],floors['basement']
                detail=f"The ground-floor shop measures {ground['area_sqft']:,.0f} sq ft, with a further {basement['area_sqft']:,.0f} sq ft in the basement. The basement should be valued separately from the ground-floor selling space."
                blocks+=[p(detail)]+cite(ground['evidence']+basement['evidence'])
                break
            detail=f"The quoted floor area is {area['area_sqft']:,.0f} sq ft."
            if area['rent_per_sqft'] is not None:
                detail+=f" The {area['rent_basis']} annual rent equates to {cash(area['rent_per_sqft'])} per sq ft on that area."
            elif vacant and price:
                detail+=f" The purchase price equates to {cash(price/area['area_sqft'])} per sq ft before acquisition costs and works."
            detail+=' '+area['area_basis'].rstrip('.')+'.'
            blocks+=[p(detail)]+cite(area['evidence'])
        company=public.get('company')
        if company:
            detail='Companies House records the tenant’s incorporation on '+natural_date(company['incorporated'])+'.'
            if company.get('first_accounts_due') and company['first_accounts_due'] >= date_text:
                detail+=' Its first accounts are not due until '+natural_date(company['first_accounts_due'])+'.'
                detail+=' A rent deposit or guarantor would therefore be important evidence when assessing the security behind the rent.'
            blocks+=[p(detail)]+cite([company['source']])
        for epc in public['energy'][:1]:
            blocks+=[p(f"The marketing brochure gives {epc['address']} an Energy Performance Certificate (EPC) rating of {epc['rating']} ({epc['score']}). The certificate itself is needed to check its date and the floors it covers.")]+cite([epc['source']])
        if sale or analysis['market'] or not report.get('guide'):blocks.append(h('Auction price'))
        if sale:blocks+=[p('The auctioneer reports a sale at '+cash(price)+'.')]+cite(record_ref(sale))
        if report.get('guide') and (sale or price != report.get('guide')):
            blocks.append(p('The '+('earlier auction guide was ' if sale else 'auction guide is ')+cash(report['guide'])+(' to '+cash(report['guide_upper']) if report.get('guide_upper') and report['guide_upper']!=report['guide'] else '')+'.'))
            guide_record=next((r for r in external if r.get('kind')=='subject_particulars' and r.get('field')=='guide_price' and compact(r.get('subject')).casefold()==compact(report['property']).casefold()),None)
            if guide_record:blocks+=cite(record_ref(guide_record))
        m=next((x for x in analysis['market'] if x['record'] in achieved),None) or next(iter(analysis['market']),None)
        if m:
            blocks+=[p(m['body']+' Differences in location, accommodation and lease terms mean it cannot establish this property’s value on its own.')]+cite(m['evidence'])
        if not sale and not m and not report.get('guide'):
            if prior_sale:blocks+=[p('The auctioneer reports that the property sold before the auction. No sale price is shown.')]+cite(record_ref(prior_sale))
            else:blocks.append(p('A purchase price is needed before the rental return can be calculated.'))
        blocks.append(p('This is an initial property investment snapshot. No legal pack was analysed. Gross yields exclude purchase expenses, repairs, empty periods, borrowing and tax.','caption'))
        return finish([{'title':'Free Property Snapshot','blocks':blocks}],[],'free_snapshot','Free Property Snapshot')
    incomplete=not inv.get('income_reconciled') and inv.get('market',{}).get('price_support')=='inconclusive' and inv.get('market',{}).get('erv_support')=='inconclusive'
    if incomplete:
        header[0]=p('AUCTION GEEK  /  RESEARCH UPDATE / NO CHARGE','kicker')
        blocks=header+[h('The pack does not yet support a full investment report'),p('We found documents that need to be read together before the current rent and ownership can be established. Some may describe earlier arrangements, rather than extra lettings. Adding their rent figures would give a misleading picture.'),p(analysis['opening']),h('What the documents do tell us')]
        blocks += schedule_blocks(report, 'income', reference_index)
        commercial=[d for d in ds if d.get('document') and not d.get('residential_reversion')]
        substitutions=[c for c in analysis['cards'] if c['kind']=='rent_substitution']
        for c in substitutions:blocks+=section(c)
        for di,d in enumerate(commercial[:3],1):
            label=d['label'] if 'unresolved' not in d['label'].lower() else f'Lease record {di}'
            blocks+=[p(label+': '+(f"The document records {money(d['annual_rent'])} annual rent. " if d.get('annual_rent') is not None else 'The current annual rent cannot be established from this document alone. ')+lease_terms(d),'small')]+cite(d.get('evidence'))
        for f in analysis['findings']:
            if 'different lease rent amounts' in f['title'].lower():
                amounts=list(dict.fromkeys([x.rstrip(',') for x in re.findall(r'£[\d,]+(?:\.\d{1,2})?',f.get('finding',''))]))
                if amounts:blocks+=[p('The lease material contains '+ ' and '.join(amounts)+'. These figures may relate to different periods or arrangements. The current amount cannot be selected safely until the later documents are checked.','small')]+cite(f.get('evidence'))
        other=[c for c in analysis['cards'] if c['kind'] not in ('interaction','rent_substitution') and c['id'] not in ('income-unreconciled','lease-extent-unresolved')]
        # A no-charge outcome is not permission to hide a known purchase cost
        # or lease restriction. Pagination checks retain the length limit.
        for c in other:blocks+=section(c)
        # Never silently omit an unfamiliar material issue just to make it short.
        if analysis['unedited_findings']:
            topics=sorted({f.get('topic','document') for f in analysis['unedited_findings']})
            blocks.append(p('Other findings about '+', '.join(topics)+' still need a clear, checked explanation. They have not been treated as settled conclusions.'))
        blocks+=[h('Why this matters to a buyer'),p('Until the documents are matched to the correct premises and dates, we cannot say which income continues after purchase or which costs the buyer takes on. Independent market evidence is also incomplete. A high advertised yield would not resolve these gaps.'),h('What is needed next'),p('The current leases, later changes, title plans and rent receipts need checking together, followed by relevant completed sales and lettings. This research update is free; a completed £19 Investment Report cannot yet be provided.')]
        return finish([{'title':'Research update','blocks':blocks}],[],'insufficient_evidence','Research update - no charge')
    # The summary cites its principal lease; detailed findings carry their own
    # sources on the following pages, avoiding a detached source-key paragraph.
    from acquisition_memorandum import transaction_summary
    page1=header+[transaction_summary(report, finance)]+overview(analysis['ownership'])
    if heritage:page1+=cite(record_ref(heritage),'Listed building status')
    page1+=[h('The investment in plain English'),p(analysis['opening']),p(analysis['assessment'])]
    if principal:page1+=cite(principal.get('evidence',[])+[e for b in principal.get('breaks',[]) for e in b.get('evidence',[])],'Main income and lease terms')
    if analysis['priority_summary']:page1.append(p(analysis['priority_summary']))
    page1+=[h('Before making an offer'),p('The rent must be collectable, the space being sold must match the income, and the buyer must be able to fund repairs and any empty period. Those checks matter more than the headline percentage.')]
    if sale:page1+=[p('The auctioneer reports a sale at '+cash(price)+'.','small')]+cite(record_ref(sale))
    if report.get('guide'):
        page1.append(p('The earlier guide was '+cash(report['guide'])+(' to '+cash(report['guide_upper']) if report.get('guide_upper') and report['guide_upper']!=report['guide'] else '')+'. It is separate from the reported sale price used here.','small'))
    page2=[h('Where the income comes from')] + schedule_blocks(report, 'income', reference_index)
    events,unresolved=lease_events(ds)
    if events:
        page2+=[chart('When the main lease terms change','timeline',events),p('An early termination right allows a tenant to leave if the lease conditions are met; it is not a prediction that they will leave. A rent review is an opportunity to reassess the rent, not a guaranteed increase.','small')]+cite([e for x in events for e in x['evidence']])
    for d in ds:
        if not d.get('document') or d.get('residential_reversion'):continue
        page2+=[h(d['label']),p(lease_terms(d),'small')]+cite([e for b in d.get('breaks',[]) for e in b.get('evidence',[])])
        security=next((s for s in analysis['underwriting']['tenant_security'] if s['unit']==d['label']),None)
        if security and security['contractual_tenant']:
            page2+=[p('The contractual tenant is '+security['contractual_tenant']+'. The trading name alone does not identify who owes the rent.','small')]+cite(security['evidence'])
        for event in analysis['underwriting']['lease_horizons']:
            if event['unit'] != d['label'] or event['past_event']:continue
            detail=(f"The break is {event['months_until']} complete months after this assessment date. " if event['months_until'] is not None and event['months_until'] <= 24 else '')
            if event['coincident_rent_review']:
                detail+='The rent review falls on the same date. It will not preserve the tenancy if the tenant validly exercises the break.'
            if detail:page2+=[p(detail,'small')]+cite(event['evidence'])
    # Ground rents, including unknown amounts, are already shown in the schedule.
    # Select by source finding type, not a case-specific identifier.
    arrears=next((c for c in analysis['cards'] if c['id'].startswith('cpse-rent-arrears')),None)
    if arrears:page2+=[p(arrears['body'],'small')]+cite(arrears['evidence'])
    page3=[h('Building and legal issues that could affect the purchase')]
    page3 += schedule_blocks(report, 'property', reference_index)
    main_ids={'ownership-extent','repair-allocation'}
    selected=[c for c in analysis['cards'] if c['id'] in main_ids or c['id'].startswith(('cover-hazard','fire-safety-','asbestos-')) or (c['kind']=='additional_review' and any(f['id'] in c['finding_ids'] and f['materiality']=='decision_gate' for f in analysis['findings']))]
    for c in selected:page3+=section(c)
    if not selected:page3.append(p('The available evidence does not establish the building’s condition or the costs that will fall to the landlord. A current survey, insurance quotation and review of the repair clauses are needed to complete the purchase budget.'))
    page4=[h('What the market evidence says about the price')]
    areas=analysis['underwriting']['accommodation']
    if areas:
        page4+=[table(['Advertised accommodation','Area (sq ft)','Annual rent','Rent / sq ft'],[[r['label'],f"{r['area_sqft']:,.0f}",cash(r['annual_rent']),cash(r['rent_per_sqft'])] for r in areas],[.43,.16,.21,.2]),p('These calculations use the quoted areas and rent bases. Ground-floor sales space and basement storage need separate comparison; these totals are not a measured or zoned rental valuation.','caption')]
        page4+=cite([e for r in areas for e in r['evidence']])
    if achieved and yield_value is not None:
        page4+=[chart('Annual rent divided by sale price','yield',[[report['property'].split(',')[0],yield_value]]+[[r.get('address') or r['source']['title'],ratio(r['rent'],r['price'])] for r in achieved[:3]]),p('These are gross yields before costs and rent concessions. A higher percentage can reflect greater risk; it does not by itself mean a bargain.','small')]
    else:
        rental=[r for r in records if r.get('kind') in ('rental_comparable','subject_asking_rent') and r.get('rent') and r.get('area_sqft')]
        if len(rental)>1:page4+=[chart('Rent per quoted square foot','comparables',[[r.get('address') or r['source']['title'],r['rent']/r['area_sqft'],r.get('rent_basis','unconfirmed')] for r in rental]),p('The figures use the quoted areas. Basements and sales floors are not necessarily equally useful to a tenant.','small')]
    for m in [x for x in analysis['market'] if x['record'] in achieved][:2]:
        r=m['record'];page4+=[p(m['body'])]
        terms=' '.join(t.get('quote','') for t in m['terms']);context=' '.join(t.get('source',{}).get('text','') for t in m['terms'])
        differences=[]
        if 'prime pedestrianised pitch' in context.lower():differences.append('The auctioneer describes a prime pedestrianised shopping location.')
        elif 'pedestrianised town centre location' in context.lower():differences.append('The particulars describe a pedestrianised town-centre location.')
        area=re.search(r'Total Area[^()]*\(([\d,]+) sq ft\)',context,re.I) or re.search(r'([\d,]+) sq ft',context)
        if area:differences.append(f"The quoted area is {area[1]} square feet; the space actually producing the rent needs checking.")
        if re.search(r'upper parts are sold off',context,re.I):differences.append('The upper floors have been sold on a long lease.')
        elif 'entirely let to one tenant' in context.lower():differences.append('One tenant rents the whole building, including the upper floors.')
        expiry=re.search(r'expiring\s+(\d{2}\.\d{2}\.\d{4})',terms,re.I)
        from datetime import datetime
        if expiry:differences.append('The lease ends on '+datetime.strptime(expiry[1],'%d.%m.%Y').strftime('%d %B %Y').lstrip('0')+(' with a tenant break in year five.' if re.search('break option in the fifth year',terms,re.I) else '.'))
        explicit_break=re.search(r"Tenant.s option to break\s+(\d{2}\.\d{2}\.\d{4})",terms,re.I)
        if explicit_break:differences.append('The tenant can end the lease on '+datetime.strptime(explicit_break[1],'%d.%m.%Y').strftime('%d %B %Y').lstrip('0')+', subject to the lease conditions.')
        concession=re.search(r'rent free period until\s+([A-Za-z]+\s+20\d{2})',terms,re.I)
        if concession:differences.append('A rent-free period until '+concession[1]+' reduced the cash collected around the sale.')
        uplift=re.search(r'fixed rental uplift[^.]*',terms,re.I)
        if uplift:differences.append('The particulars also state a '+uplift[0].strip()+'. The sale comparison uses the rent advertised at that sale; the exact uplift date must be checked before describing the later rent.')
        if re.search('full repairing and insuring',terms,re.I):differences.append('The tenant is said to carry repair and insurance costs, but the full clauses and building condition have not been checked.')
        elif 'not been internally inspected by savills' in context.lower():differences.append('Savills had not inspected internally; condition and repair costs remain unverified.')
        if differences:page4+=[p(' '.join(differences),'small')]
        page4+=cite(m['evidence'])
    if achieved and yield_value is not None:
        spread=yield_value-ratio(achieved[0]['rent'],achieved[0]['price'])
        page4.append(p(f'The {abs(spread):.2f}-percentage-point yield gap against the first sale is useful context, not a price adjustment. Trading position, usable space, tenant strength and landlord costs differ. These transactions do not establish that this property is cheap or support a reliable value if it becomes empty.','small'))
    page4.append(h('Could a replacement tenant pay the same rent?'))
    rentals=[x for x in analysis['market'] if x['record'].get('rent') is not None and x['record'].get('price') is None]
    own=next((m for m in rentals if m['record']['kind']=='subject_asking_rent'),None)
    neighbouring=next((m for m in rentals if m['record']['kind']=='rental_comparable'),None)
    if own and neighbouring:
        a,b=own['record'],neighbouring['record']
        page4.append(p(f"The main shop has been marketed at {money(a['rent'])} a year"+(f" for {a['area_sqft']:,.0f} square feet" if a.get('area_sqft') else '')+f", while another unit is advertised at {money(b['rent'])}"+(f" for {b['area_sqft']:,.0f} square feet" if b.get('area_sqft') else '')+'. These are asking rents. Differences in layout, storage space and incentives prevent a direct comparison.','small'))
        page4+=cite(own['evidence']+neighbouring['evidence'])
    else:
        for m in rentals[:2]:page4+=[p(m['body'],'small')]+cite(m['evidence'])
    if not achieved:
        for m in [x for x in analysis['market'] if x not in rentals][:2]:page4+=[p(m['body'],'small')]+cite(m['evidence'])
    page4.append(p('A local letting assessment should establish a replacement rent, likely incentives and time to find a tenant, taking account of competing premises.','small'))
    page5=[h('The cash needed and the cost of losing a tenant')]
    costrows=[[price_label,cash(price)]]
    for c in report.get('costs',[]):costrows.append([c['label'],cash(c['amount'])]);refs(c.get('evidence'))
    if finance['illustrative_tax']:costrows.append(['Illustrative purchase tax',cash(finance['illustrative_tax']['amount'])]);refs([finance['illustrative_tax']['source']])
    if finance['capital_basis']:costrows.append(['Subtotal before unpriced costs',cash(finance['capital_basis'])])
    page5+=[table(['Purchase cash','Amount'],costrows,[.74,.26]),p('The subtotal is not the full budget. Buyer’s legal and survey fees, finance, any VAT requirement and initial work still need pricing. The tax illustration assumes a single freehold non-residential or mixed-use purchase; the solicitor must check the tax treatment and any additional amounts that are taxable.','small')]
    page5+=cite([e for c in report.get('costs',[]) for e in c.get('evidence',[])]+([finance['illustrative_tax']['source']] if finance['illustrative_tax'] else []))
    from acquisition_financials import ownership_scenarios
    ownership = ownership_scenarios(rent, finance['capital_basis'],
        principal_rent=principal['annual_rent'] if principal else None)
    if ownership:
        page5 += [h('Income after ownership costs'), table(
            ['Illustrative scenario', 'Cash remaining', 'Cash return'],
            [[s['label'], cash(s['cash_remaining']), f"{s['cash_return_pct']:.2f}%"] for s in ownership], [.52,.24,.24]),
            p('The £5,000 and £10,000 annual costs are illustrative unrecovered expenditure, not estimates. '
              'The £25,000 repair affects only the year it is paid. Vacancy holds the £5,000 annual allowance constant. '
              'Returns use identified acquisition expenditure; finance, income tax and additional unpriced costs are excluded.', 'caption')]
    capacities=[c for c in finance['cost_capacity'] if c['hurdle_pct'] in (10,12)]
    if capacities:
        page5+=[table(['Illustrative annual return','Annual income needed','Allowance for unrecovered costs'],[[str(c['hurdle_pct'])+'%',cash(c['required_annual_cash']),cash(c['annual_cost_capacity'])] for c in capacities],[.29,.29,.42]),p('The allowance is the stated rent less the income needed for that return on the purchase subtotal. It is not an expense forecast. A negative figure is a shortfall even before expenses; additional purchase costs or lost rent reduce the allowance.','caption')]
    if profile.get('listed') and profile.get('jurisdiction')=='England':
        page5+=[p('Listed buildings can qualify for relief from empty-property business rates until reoccupied. Ask the council to confirm that this space qualifies; a standard business-rates bill has not been assumed.','small')]+cite([{'document':'GOV.UK: empty-property rates relief, checked 18 October 2026','url':'https://www.gov.uk/business-rates-relief/empty-property-relief'}])
    for c in finance['historical_costs'][:1]:
        period=re.sub(r'^01/01 - 31/12/(\d{4})$',r'\1',c['period'])
        page5+=[p(f"The accounts record {money(c['amount'])} of building expenditure for {period}. This is past spending, not a forecast of the buyer’s costs. We have not established how much was recovered from tenants or whether the same work will recur.",'small')]+cite(c['evidence'])
    page5+=[h('Our investment assessment'),p(analysis['conclusion'])]
    # No unfamiliar material issue is hidden in order to achieve the page target.
    appendix=[h('Further checks before purchase'),p('Supporting document names and page references are collected at the end. These additional checks should be read alongside the main assessment.','small')]
    selected_ids={c['id'] for c in selected}|{'income-building-interaction'}
    remaining=[c for c in analysis['cards'] if c['id'] not in selected_ids and not c['id'].startswith(('epc-','cpse-rent-arrears','income-unreconciled'))]
    for c in remaining:appendix+=[h(c['title']),p(c['body'],'small')]+cite(c['evidence'])
    for f in analysis['unedited_findings']:
        appendix+=[h('Further review: '+f['title']),p(f.get('summary') or f['finding'],'small'),p(f['consequence'],'small'),p('This finding still needs editorial review. The report must be held before customer release.','small')]+cite(f.get('evidence'))
    return finish([{'title':t,'blocks':b} for t,b in zip(['The investment','Income','Building and ownership','Market evidence','Cash and conclusion'],[page1,page2,page3,page4,page5])],[{'title':'Evidence appendix','blocks':appendix}],'review_required','Investment Report - review copy')
