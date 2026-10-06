"""Transaction-centred, source-bound acquisition intelligence above the pack reader.

This layer reconciles extracted evidence. It never asks a language model to invent
missing legal/financial facts, and preserves the complete underlying evidence.
"""
import re,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from acquisition_chronology import lease_chronology

SECTIONS=[('buying','What you are buying'),('numbers','The numbers'),('view','Our first-pass view'),('covenant','Tenant & covenant'),('lease','The lease — in plain English'),('cpse','What the seller has told you / CPSE'),('title','Title & what is actually included'),('conditions','Special Auction Conditions'),('searches','Searches & property risks'),('costs','Costs Auction Sniper found'),('concerns','What concerns us'),('opportunities','Opportunities'),('unknowns','What we could not establish'),('questions','If we were buying it, the questions we would still ask'),('evidence','Full evidence')]
TOPIC_SECTION={'tenant':'covenant','rent':'lease','expiry':'lease','breaks':'lease','reviews':'lease','repairs':'lease','insurance':'lease','service':'lease','ground':'lease','title':'title','plans':'title','rights':'title','conditions':'conditions','completion':'conditions','deposit':'conditions','vat':'conditions','seller-costs':'costs','buyer-fees':'costs','searches':'searches','environment':'searches','planning':'searches','epc':'searches'}
def norm(x):return re.sub(r'\s+',' ',str(x or '')).strip()
def money(v):return '£'+format(float(v),',.0f') if isinstance(v,(int,float,Decimal)) else 'Not established'
def amount(text):
    m=re.search(r'£\s*([\d,]+(?:\.\d{1,2})?)',text or '');return float(m.group(1).replace(',','')) if m else None

def build_acquisition(model,catalogue=None):
    c=catalogue or {};source_findings=model.get('findings',[]);facts=[f for f in source_findings if f.get('fact')]
    findings=[];groups=defaultdict(list)
    for f in source_findings:groups[f['title']].append(f)
    def add(id,title,found,why,meaning,next_step,sources,topic='concerns',severity='NEEDS CHECKING',impact=None):
        unique=[];seen=set()
        for e in sources:
            key=(e.get('document'),e.get('page'),norm(e.get('excerpt')))
            if key not in seen:unique.append(e);seen.add(key)
        findings.append({'id':id,'title':title,'found':found,'why':why,'meaning':meaning,'impact':impact,'next_step':next_step,'evidence':unique,'section':topic,'severity':severity})
    def evidence_for(title):return [e for f in groups.get(title,[]) for e in f.get('evidence',[])]
    def summary_for(title):return ' '.join(dict.fromkeys(f.get('summary','') for f in groups.get(title,[])))
    guide=c.get('guide') or c.get('guide_price');rent=c.get('rent') if c.get('rent') is not None else c.get('annual_rent');upper=c.get('guide_price_upper')
    if not isinstance(guide,(int,float)):guide=None
    if not isinstance(rent,(int,float)) or re.search(r'^vacant',str(c.get('occupation','')),re.I):rent=None
    tenant=c.get('tenant');company_number=None;tenant_evidence=evidence_for('Tenant named in the lease')
    if tenant_evidence:
        text=' '.join(e['excerpt'] for e in tenant_evidence)
        m=re.search(r'\(2\)\s*([A-Z][A-Z ()&.,’\'-]+?LIMITED)\s*\(registered',text)
        if m:tenant=m.group(1)
        n=re.search(r'registered (?:number|no\.?)[\s:]*(\d{8}|[A-Z]{2}\d{6})',text,re.I)
        if n:company_number=n.group(1).upper()
    calculations=[]
    if guide and rent is not None:
        calculations.append({'label':'Gross Initial Yield (GIY)','value':f'{rent/(upper or guide)*100:.1f}%','working':f'{money(rent)} current annual rent ÷ {money(upper or guide)} '+('upper guide' if upper else 'guide')+' × 100. Before fees, tax, voids and costs.','basis':'Published current particulars; reconcile with the operative lease and payment ledger.'})
    dep=summary_for('Deposit recorded in the sale conditions');deposit=None
    m=re.search(r'(\d+(?:\.\d+)?)%',dep)
    if m and guide:
        deposit=guide*float(m.group(1))/100
        calculations.append({'label':'Deposit at guide','value':money(deposit),'working':f'{m.group(1)}% × {money(guide)}. Part of the purchase price, not an additional cost.','evidence':evidence_for('Deposit recorded in the sale conditions')})
    costs=[]
    ev=evidence_for('Additional seller fees')
    if ev:
        text=' '.join(e['excerpt'] for e in ev);m=re.search(r'(?:contribute|pay (?:the )?seller(?:[’\x27]s)? (?:legal|agent(?:[’\x27]s)?) (?:fees|costs)(?: of)?)\s*£\s*([\d,.]+)\s*(plus VAT|\+\s*VAT|including VAT|inclusive of VAT)?',text,re.I)
        if m:
            base=float(m.group(1).replace(',',''));extra=bool(m.group(2) and re.search(r'plus|\+',m.group(2),re.I));vat=round(base*.2,2) if extra else 0;total=base+vat
            costs.append({'label':'Seller’s legal / agent contribution','amount':total,'base':base,'vat':vat,'evidence':ev,'basis':'20% VAT calculation' if extra else 'Published amount'})
            calculations.append({'label':'Seller-cost contribution','value':money(total)+(' including VAT' if m.group(2) else ''),'working':money(base)+(f' + {money(vat)} VAT at 20% = {money(total)}.' if extra else '.'),'evidence':ev})
            meaning=(f'At a 20% VAT rate, the stated fixed contribution models to {money(total)}.' if extra else f'The fixed contribution is {money(total)}'+(' including VAT.' if m.group(2) else ', as published.'))
            add('seller-fee','Budget for the seller’s costs',norm(summary_for('Additional seller fees')), 'This is payable in addition to the price and the auctioneer’s own fee.',meaning,'Request a completion statement confirming the fixed contribution and all other charges.',ev,'costs',impact=money(total))
    fee_evidence=evidence_for('Auctioneer fee recorded in the sale conditions')
    fee_terms={}
    for f in groups.get('Auctioneer fee recorded in the sale conditions',[]):
        m=re.search(r'fee(?: of)?\s*£\s*([\d,.]+)(?:\s*(plus VAT|\+\s*VAT|including VAT|inclusive of VAT))?',f.get('summary',''),re.I)
        if m:
            base=float(m[1].replace(',',''));extra=bool(m[2] and re.search(r'plus|\+',m[2],re.I));vat=round(base*.2,2) if extra else 0
            fee_terms[(base,vat)]=(base+vat,extra,bool(m[2]))
    if len(fee_terms)==1:
        (base,vat),(total,extra,vat_stated)=next(iter(fee_terms.items()))
        costs.append({'label':'Auctioneer fee in sale conditions','amount':total,'base':base,'vat':vat,'basis':'Lot-specific sale conditions','evidence':fee_evidence})
        calculations.append({'label':'Auctioneer fee','value':money(total)+(' including VAT' if vat_stated else ''),'working':money(base)+(f' + {money(vat)} VAT at 20% = {money(total)}.' if extra else ', as published.'),'evidence':fee_evidence})
    elif len(fee_terms)>1:
        add('fee-conflict','Different auctioneer fees need reconciliation',summary_for('Auctioneer fee recorded in the sale conditions'),
            'Selecting one amount could understate the acquisition cost.','No single auctioneer fee has been added to the cost total.',
            'Confirm which sale conditions and addendum govern this lot.',fee_evidence,'costs')
    elif isinstance(c.get('auctioneer_fee'),(int,float)):
        costs.append({'label':'Estimated auctioneer fee','amount':c['auctioneer_fee'],'basis':'Verified auctioneer terms, calculated at guide','evidence':[]})
    if costs:
        known=sum(x['amount'] for x in costs);calculations.append({'label':'Quantified additional costs','value':money(known),'working':' + '.join(money(x['amount']) for x in costs)+'. Excludes SDLT/LTT/LBTT, your advisers, unquantified searches, arrears and other liabilities.'})
    if 'Buyer may have to fund rent arrears' in groups:
        add('arrears','The buyer may have to fund arrears',summary_for('Buyer may have to fund rent arrears'),'Paying the seller for unpaid rent transfers recovery risk to the buyer.','No arrears amount is established. This is a contingent liability, not proof that the tenant is in arrears.','Obtain a dated tenant rent ledger and confirm the amount payable and rights transferred.',evidence_for('Buyer may have to fund rent arrears'),'concerns','CRITICAL / RED FLAG','Unquantified; add the actual balance to cash required if applicable.')
    if 'Search-cost reimbursement' in groups:
        add('search-cost','Search charges remain unquantified',summary_for('Search-cost reimbursement'),'These can increase completion cash beyond the quoted buyer fee.','The documents allocate the cost but the recovered clause does not establish an amount.','Request the search/disbursement invoices and VAT-inclusive total.',evidence_for('Search-cost reimbursement'),'costs')
    if 'VAT depends on TOGC conditions' in groups and 'Seller states no option to tax' not in groups:
        impact=f'If 20% VAT applied to the {money(guide)} guide, the initial VAT cash requirement would be {money(guide*.2)}. Recoverability is not assumed.' if guide else None
        add('vat-togc','VAT is conditional on the transaction structure',summary_for('VAT depends on TOGC conditions'),'TOGC means Transfer of a Going Concern: qualifying business transfers can be treated differently for VAT.','An option-to-tax document and a TOGC clause do not by themselves prove that this buyer and transaction meet every condition.','Confirm the buyer’s VAT/option-to-tax position, deadlines and the seller’s evidence before committing.',evidence_for('VAT depends on TOGC conditions')+evidence_for('VAT / Option to Tax / TOGC'),'conditions',impact=impact)
    elif 'VAT depends on TOGC conditions' in groups and 'Seller states no option to tax' in groups:
        add('vat-conflict','Different VAT statements need reconciliation',summary_for('Seller states no option to tax')+' '+summary_for('VAT depends on TOGC conditions'),
            'The cash required can change materially depending on which provision governs this sale.',
            'The report does not select a VAT treatment from conflicting sale-condition statements.',
            'Confirm the operative sale conditions, any addendum and the seller’s VAT position.',
            evidence_for('Seller states no option to tax')+evidence_for('VAT depends on TOGC conditions'),'conditions')
    if 'Restrictions on enquiries or objections' in groups:
        add('enquiries','Resolve material questions before bidding',summary_for('Restrictions on enquiries or objections'),'The contractual ability to object after the auction may be restricted.','The restriction is part of the proposed bargain. It does not itself prove a title defect.','Obtain answers to the specific outstanding title, arrears and cost questions before bidding.',evidence_for('Restrictions on enquiries or objections'),'conditions')
    rents=groups.get('Rent amount recorded in this document',[])
    if rent and any(amount(f.get('summary',''))==rent for f in rents):
        add('rent-agreement','Catalogue and lease amount agree',f'The current particulars state {money(rent)} p.a.; at least one supplied lease extract records the same annual amount.','Agreement is useful evidence, but it is different from proof of payment.','Use the published current rent for GIY; do not substitute historic or concessionary figures.','Reconcile the operative lease, expiry and any subsequent variation with the current payment ledger.',[e for f in rents if amount(f.get('summary',''))==rent for e in f['evidence']],'lease','INFORMATION')
    if 'Concessionary rent period' in groups:
        add('rent-concession','A rent concession is not the current annual rent',summary_for('Concessionary rent period'),'A lease may contain both an annual rent and a time-limited concession. Treating the concession as continuing would misstate income.','The concession must be placed against the operative commencement date. OCR uncertainty in that date remains explicit; the report does not silently calculate a false expiry.','Confirm the exact commencement date and whether the concession has ended, then compare payments with the annual rent.',evidence_for('Concessionary rent period')+evidence_for('Lease term recorded')+evidence_for('Rent amount recorded in this document'),'lease','INFORMATION')
    proprietors=groups.get('Registered proprietor recorded',[])
    if len({f.get('summary') for f in proprietors})>1:
        add('title-relationships','Different title owners are not automatically a contradiction','Different registered proprietor names occur in the pack’s separate title registers.','A commercial investment can include freehold and occupational leasehold titles with different owners.','Compare each title’s estate, plan and lease relationship before comparing its owner to the seller. Do not treat the tenant’s registered interest as evidence that the seller cannot sell the freehold.','Confirm a title-by-title sale schedule showing the estate sold, tenant demise, retained land and registration chain.',[e for f in proprietors for e in f['evidence']]+evidence_for('Title number in this document'),'title','INFORMATION')
    # Only precise, evidenced facts enter the concise narrative. Keyword matches
    # remain in Full evidence instead of being reissued as dozens of warnings.
    handled={'Additional seller fees','Auctioneer fee recorded in the sale conditions','Deposit recorded in the sale conditions','Rent amount recorded in this document','Registered proprietor recorded','Title number in this document','Concessionary rent period','Tenant named in the lease','VAT depends on TOGC conditions'}
    for title,items in groups.items():
        fs=[f for f in items if f.get('fact')]
        if title in handled or not fs:continue
        topic=fs[0]['topic'];add('fact-'+hashlib.sha256(title.encode()).hexdigest()[:10],title,' '.join(dict.fromkeys(f['summary'] for f in fs)),
            'This is a specific term or observation recovered from the supplied evidence.','Read its qualifications and date alongside the original; it is not a guarantee of the property’s current condition.',fs[0]['action'],[e for f in fs for e in f['evidence']],TOPIC_SECTION.get(topic,'lease'),'INFORMATION')
    documents,lease_reconciliation=lease_chronology(model)
    differing_rents={r for lease_record in lease_reconciliation for r in lease_record['rent_amounts']}
    if len(lease_reconciliation)>1 and len(differing_rents)>1:
        evidence=[e for lease_record in lease_reconciliation for e in lease_record['evidence']]
        found='; '.join(record['document']+': '+', '.join(money(r)+' p.a.' for r in record['rent_amounts']) for record in lease_reconciliation if record['rent_amounts'])
        add('lease-rent-chronology','Separate leases record different rent amounts',found,
            'Using an earlier or concessionary amount as current rent changes the apparent investment yield.',
            'A later document does not automatically supersede every earlier document. The report keeps each rent attached to its source and does not select the highest amount as current income.',
            'Confirm which lease, variations and concessions govern the current letting, and reconcile the current rent ledger.',evidence,'lease','NEEDS CHECKING')
    cpse=[d for d in documents if 'cpse' in d.get('type','').lower()]
    cpse_text=('CPSE means Commercial Property Standard Enquiries. Qualified replies such as “not known” or “buyer to rely on own enquiries” are not automatically defects. Only material gaps are raised below.' if cpse else 'Separate CPSE replies were not identified. The rest of the supplied pack has still been used for the transaction facts, costs and lease evidence. Absence of a CPSE document is not the same as absence of every answer.')
    lease=summary_for('Lease term recorded');completion=summary_for('Contractual completion period');tenure=c.get('tenure')
    if len(lease_reconciliation)>1:
        lease=f'{len(lease_reconciliation)} separate lease documents; operative terms require reconciliation.'
    description=f"{('A '+tenure.lower()+' commercial property') if tenure else 'A commercial property'} at {model['property']}"
    if tenant:description+=f', with {tenant} named as tenant'+(' in the supplied lease' if tenant_evidence else ' in the auction particulars')
    description+='.'
    unknowns=list(dict.fromkeys(model.get('missing',[])))
    if not tenant:unknowns.append('Exact current legal tenant has not been established.')
    if not guide:unknowns.append('A current guide price was not supplied with this pack.')
    questions=[]
    for f in findings:
        if f['severity']=='INFORMATION' and f['id'] not in ('rent-concession','title-relationships'):continue
        questions.append({'question':f['next_step'],'who':'Seller / auctioneer for the evidence; purchaser’s solicitor or tax adviser for its contractual effect','why':f['why'],'established':f['found'],'finding_id':f['id']})
    deep=next((f for id in ('rent-concession','title-relationships','seller-fee','vat-togc') for f in findings if f['id']==id),None)
    priority=sorted(findings,key=lambda f:({'CRITICAL / RED FLAG':0,'NEEDS CHECKING':1,'INFORMATION':2}[f['severity']],f['id']))
    opportunities=[f for f in findings if f['id']=='rent-agreement']
    return {'schema_version':'3.0','engine':model.get('engine'),'product':'Auction Sniper Acquisition Intelligence','report_id':model['report_id'],'property':model['property'],'created_at':model['created_at'],
        'what_you_are_buying':description,'guide':guide,'guide_upper':upper,'rent':rent,'tenant':tenant,'company_number':company_number,'tenant_evidence':tenant_evidence,'tenure':tenure,
        'lease':lease or 'Operative lease term not established','completion':completion or 'Completion deadline not established','deposit':deposit,
        'vat':('Different VAT statements require reconciliation.' if 'VAT depends on TOGC conditions' in groups and 'Seller states no option to tax' in groups else summary_for('Seller states no option to tax') or summary_for('VAT depends on TOGC conditions') or 'Transaction VAT treatment not established'),'calculations':calculations,'costs':costs,
        'first_pass':f'{len(findings)} consolidated findings from {model.get("coverage",{}).get("text_documents",0)} documents. '+('Quantified costs and contingent liabilities need to be reflected in your bid.' if costs else 'The report separates evidenced facts from remaining gaps; it is not a buy recommendation.'),
        'findings':priority,'deep_dive':deep,'cpse':cpse_text,'opportunities':opportunities,'unknowns':unknowns,'questions':questions,'documents':documents,
        'lease_reconciliation':lease_reconciliation,'coverage':model.get('coverage',{}),'sections':SECTIONS,'evidence_review':model,'disclaimer':'Acquisition research, not legal, tax or valuation advice. Verify material conclusions against the source documents and with the appropriate professional.'}

def snapshot(report):
    """Actual server projection: the paid payload is not sent hidden in the DOM."""
    out={k:v for k,v in report.items() if k not in ('evidence_review','findings','documents','questions','unknowns','opportunities','costs','market_context','lease_reconciliation')}
    deep_id=(report.get('deep_dive') or {}).get('id')
    out['findings']=[f for f in report['findings'] if f.get('id')!=deep_id][:3]
    shown={f['id'] for f in out['findings']}
    if deep_id:shown.add(deep_id)
    out['additional_findings']=sum(f['id'] not in shown for f in report['findings']);out['access']='snapshot'
    out['sections']=SECTIONS[:3];return out
