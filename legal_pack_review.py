"""Document-grounded report: quoted clauses, explicit uncertainty and actions.

No remote model, document instructions or arbitrary document URLs are executed.
Topic matches are review leads; only narrow, evidenced facts become summaries.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime,timezone
import hashlib,re

VERSION='2.0'
TOPICS=[
 ('title','Title / tenure',r'\bfreehold\b|\bleasehold\b|title (?:number|guarantee)|registered proprietor', 'Confirm the sale extent, ownership and registration chain for every relevant title.'),
 ('rights','Charges / restrictions / easements',r'RESTRICTION:|restrictive covenant|right of way|rights of way|easement|registered charge', 'Check enforceability, discharge of charges and whether access and service rights are adequate.'),
 ('plans','Title plan / boundary issues',r'general boundaries|land edged|land tinted|land hatched|title plan|parcel of land', 'Compare the title, transfer and lease plans with the physical property. Text extraction cannot establish boundaries.'),
 ('leases','Occupational leases',r'prescribed clauses|contractual term|term of (?:\w+ )?years|lease dated|renewal tenancy', 'Identify the operative lease and all variations; distinguish earlier leases and draft terms.'),
 ('tenant','Tenant / tenancy schedule',r'current tenant|tenancy schedule|\btenant\s*[:\n]|\(2\)\s*[A-Z]', 'Reconcile the legal tenant, occupation and any assignments with the current tenancy schedule.'),
 ('rent','Current rent and historic rent',r'passing rent|current rent|annual rent|initial rent|yearly rent|rent of £|£[\d,]+[^.]{0,55}per annum', 'Confirm rent currently payable and actually collected. Earlier lease rent, proposed rent and ERV are not current income.'),
 ('expiry','Lease term / expiry',r'contractual term|term commencement|term expiry|term for which|expired on|years from|to and including', 'Check commencement, expiry and any continuation or renewal; OCR dates need confirmation against the scan.'),
 ('breaks','Break clauses',r'break (?:date|clause|notice|option)|option to (?:break|determine)|tenant.{0,80}(?:terminate|determine) this lease', 'Confirm who can break, the earliest date, notice deadline and every condition.'),
 ('reviews','Rent reviews',r'review date|rent review|reviewed rent|review of.{0,25}rent', 'Check review dates, assumptions, indexation, caps/collars and any outstanding review.'),
 ('repairs','Repairing obligations',r'keep.{0,100}(?:repair|condition)|repair and condition|repairing obligations|landlord shall.{0,80}(?:roof|structure|exterior)', 'Read tenant and landlord covenants together, including exceptions and any schedule of condition; do not infer FRI from isolated words.'),
 ('service','Service charge',r'service charge|service yard.{0,60}(?:cost|charge)|shared.{0,30}cost', 'Confirm liability, apportionment, budget, historic accounts, caps and tenant recovery.'),
 ('insurance','Insurance obligations',r'(?:landlord|seller|tenant).{0,90}insur|insurance rent|insurance premium', 'Check who insures, who pays, insured risks, excesses and when acquisition risk passes.'),
 ('ground','Ground rent',r'ground rent|head rent', 'Confirm the superior lease rent, review mechanism and any arrears. A concessionary occupational rent is not necessarily ground rent.'),
 ('vat','VAT / Option to Tax / TOGC',r'VAT is payable|VAT.{0,70}addition|option to tax|opted to tax|transfer of (?:a )?going concern|\bTOGC\b', 'Verify VAT evidence and the exact TOGC conditions before bidding; conditional wording does not establish that TOGC will apply.'),
 ('deposit','Auction deposit',r'deposit.{0,200}(?:\d+%|per cent|percent|£)|\d+%.{0,80}(?:price|deposit)', 'Confirm the deposit, deadline and stakeholder terms. It is normally part of the purchase price, not an additional acquisition fee.'),
 ('buyer-fees','Buyer’s premium / admin fee',r'buyer.{0,15}(?:premium|administration fee|admin fee)|auctioneer.{0,35}fee', 'Check lot-specific auctioneer fees, minima and VAT separately from the deposit and seller charges.'),
 ('seller-costs','Seller’s additional costs',r'(?:buyer|purchaser).{0,100}(?:contribut|cost of|pay.{0,30}arrears)|notice.{0,70}£', 'Quantify extra seller costs and liabilities, including VAT and contingent default charges.'),
 ('completion','Completion period',r'agreed completion date|working days from.{0,35}contract|completion.{0,45}\d+ (?:working )?days', 'Confirm the binding deadline and funding timetable; distinguish normal completion from notice-to-complete periods.'),
 ('conditions','Special conditions of sale',r'no (?:additional )?enquiries|no requisitions|not.{0,25}registered proprietor|no warranty|no claim|limited title guarantee', 'Resolve onerous conditions before bidding, particularly restrictions on enquiries and objections.'),
 ('searches','Searches',r'local authority search|local land charges|public sewer|water main|highway maintainable|adopted highway|coal mining', 'Check search dates, coverage, outstanding replies and any recommended further investigations.'),
 ('planning','Planning / development',r'planning permission|planning consent|enforcement notice|listed building|conservation area|change of use', 'Verify the actual consent, conditions and permitted use; a reference to planning is not evidence that the proposed development is authorised.'),
 ('epc','EPC',r'energy (?:performance|rating)|certificate reference|valid until|recommendation report', 'Confirm the rating, expiry, property extent and applicable letting requirements against the original certificate.'),
 ('environment','Environmental / flood / asbestos',r'contaminated land.{0,65}(?:pass|refer)|flood.{0,65}(?:pass|high|moderate|low)|asbestos.{0,65}(?:identified|detected|found|containing)|chrysotile|amosite|crocidolite', 'Check the report date, survey limitations, actual findings and recommended action; a search result does not replace a site survey.'),
]

def norm(text):return re.sub(r'\s+',' ',str(text or '')).strip()

def document_pages(document):
 pages=document.metadata.get('pages') or []
 if pages:return pages
 return [{'page':None,'text':document.text,'ocr':False}]

def evidence(document,page,match,context=200):
 text=norm(page['text']);start=max(0,match.start()-context);end=min(len(text),match.end()+context)
 # Keep word boundaries without manufacturing punctuation or omitted words.
 if start:start=text.find(' ',start)+1
 if end<len(text):end=text.rfind(' ',start,end)
 excerpt=text[start:end]
 return {'document':document.name,'page':page.get('page'),'excerpt':excerpt,
         'ocr':bool(page.get('ocr')),'document_sha256':document.sha256}

def build_evidence_report(property_ref,documents,ingestion,catalogue=None):
 catalogue=catalogue or {};docs=list(documents);findings=[];seen=set();questions=[]
 def add(topic,title,summary,action,ev,severity='NEEDS CHECKING',fact=False):
  key=(topic,title,ev['document'],norm(ev['excerpt']).lower())
  if key in seen:return
  seen.add(key)
  findings.append({'id':hashlib.sha256(repr(key).encode()).hexdigest()[:16],
      'topic':topic,'title':title,'summary':summary,'action':action,'severity':severity,
      'basis':'OCR text — check the original' if ev['ocr'] else 'Source text',
      'evidence':[ev],'source':ev['document'],'fact':fact})
 # High-priority sale clauses. Conditional language stays conditional.
 rules=[
 ('seller-costs','Additional seller fees',r'(?:buyer|purchaser) shall (?:also )?contribute\s*£[\d,.]+.{0,170}?(?:fees|costs)',
  'The conditions require a contribution towards seller costs.', 'Obtain a completion statement confirming this contribution, VAT and every other seller charge.','CRITICAL / RED FLAG'),
 ('seller-costs','Buyer may have to fund rent arrears',r'on completion.{0,110}?(?:buyer|purchaser).{0,60}?pay.{0,65}?arrears of rent.{0,80}',
  'The conditions require the buyer to pay the seller any rent arrears, if present, in addition to the price.', 'Obtain a current arrears ledger, quantify the exposure and ask your solicitor who bears collection risk.','CRITICAL / RED FLAG'),
 ('conditions','Restrictions on enquiries or objections',r'(?:raise no requisitions.{0,110}|no additional enquiries.{0,100}|will not provide any replies.{0,120})',
  'The conditions restrict further enquiries or objections.', 'Complete legal review and obtain essential answers before bidding; ask your solicitor about the effect of these restrictions.','CRITICAL / RED FLAG'),
 ('conditions','Seller-registration condition',r'(?:in the event.{0,100}not the registered proprietor.{0,450}|not to insist.{0,120}registered proprietor.{0,100})',
  'The contract addresses completion where the seller is not yet the registered proprietor. This does not prove that this is the present position.', 'Reconcile the named seller, current registers and transfer chain; establish whether the condition will apply.','NEEDS CHECKING'),
 ('vat','VAT depends on TOGC conditions',r'VAT is payable unless.{0,100}going concern',
  'VAT is payable unless the transaction qualifies as a TOGC.', 'Confirm the seller’s option, buyer requirements and fallback VAT cash requirement with your solicitor and tax adviser.','NEEDS CHECKING'),
 ('deposit','Deposit recorded in the sale conditions',r'\d+(?:\.\d+)?% of the price.{0,180}(?:stakeholder|deposit)',
  'The source records the deposit as a percentage of the price.', 'Check payment timing and the full deposit clause. Do not add the deposit again as a fee.','INFORMATION'),
 ('completion','Contractual completion period',r'\b\d+ working days from the contract date',
  'The source specifies a completion period measured from the contract date.', 'Ask your solicitor to confirm the actual completion date and funding deadline.','NEEDS CHECKING'),
 ('seller-costs','Search-cost reimbursement',r'(?:purchaser|buyer).{0,90}(?:cost of any searches|searches or disbursements).{0,220}',
  'The conditions require reimbursement of search costs or disbursements; the amount needs confirmation.', 'Request an itemised amount, including any costs for searches that are still outstanding.','NEEDS CHECKING'),
 ]
 for d in docs:
  pages=document_pages(d)
  if d.doc_type.value=='special_conditions':
   for page in pages:
    text=norm(page['text'])
    for topic,title,pattern,summary,action,level in rules:
     m=re.search(pattern,text,re.I)
     if m:
      if title=='Additional seller fees':summary='The conditions state: “'+norm(m.group(0))+'”. Confirm the exact calculation and VAT treatment.'
      elif title=='Contractual completion period':summary='Completion: '+norm(m.group(0))+'.'
      elif title=='Deposit recorded in the sale conditions':summary='Deposit: '+re.search(r'\d+(?:\.\d+)?%',m.group(0)).group(0)+' of the price. This is not an additional acquisition fee.'
      add(topic,title,summary,action,evidence(d,page,m,90),level,True)
  for topic,title,pattern,action in TOPICS:
   # One short lead per document/topic. All originals remain in the inventory.
   # Exclude tables of contents, generic advertisements and irrelevant document roles.
   if topic in ('title','rights','plans') and d.doc_type.value not in ('title_register','title_plan','transfer','lease','special_conditions'):continue
   if topic in ('deposit','buyer-fees','seller-costs','completion','conditions') and d.doc_type.value not in ('special_conditions','other'):continue
   if topic in ('rent','tenant','leases','expiry','breaks','reviews','repairs','service','insurance','ground') and d.doc_type.value not in ('lease','special_conditions','cpse1','cpse2','tenancy_schedule','transfer'):continue
   if topic=='epc' and d.doc_type.value!='epc':continue
   if topic=='environment' and d.doc_type.value not in ('environmental','asbestos','search'):continue
   if any(f['topic']==topic and f['source']==d.name and f['fact'] for f in findings):continue
   candidates=[]
   for page in pages:
    text=norm(page['text'])
    if re.search(r'\.{5,}',text) and 'Contents' in text[:300]:continue
    for m in re.finditer(pattern,text,re.I):
     ev=evidence(d,page,m,190)
     if len(ev['excerpt'])<55:continue
     score=0
     if re.search(r'£|\d+%|\bshall\b|\bmust\b|\btenant\b|\bproprietor\b',ev['excerpt'],re.I):score+=2
     if re.search(r'contents|glossary|definitions of|legal notice',text[:140],re.I):score-=5
     candidates.append((score,ev))
   if candidates:
    ev=max(candidates,key=lambda v:v[0])[1]
    summary='Relevant wording identified; interpretation and application to this purchase require checking.'
    if topic=='rent':summary='Rent wording identified. It may be historic, initial, proposed or reviewed rent; current passing rent is not established by this extract alone.'
    if topic=='environment':summary='Relevant survey/search wording identified. Check the dated conclusion and limitations rather than treating every risk mentioned as a finding.'
    if topic=='epc':summary='Certificate text identified. Confirm rating, date and property extent against the original.'
    add(topic,title,summary,action,ev)
 # Extra precise, source-labelled facts make current and historic leases comparable.
 for d in docs:
  if d.doc_type.value not in ('lease','special_conditions','title_register'):continue
  for page in document_pages(d):
   text=norm(page['text'])
   for topic,title,pattern,action in [
    ('title','Title number in this document',r'(?:title number(?: / Rhif teitl)?|under title number)\s*[:\n]?\s*([A-Z]{1,3}\d{3,8})','Reconcile the interest and extent of this title with all other titles and the sale conditions.'),
    ('title','Registered proprietor recorded',r'PROPRIETOR:\s*([A-Z][A-Z &()’\'-]+LIMITED)','Compare the registered proprietor with the contractual seller and any intervening transfer.'),
    ('rent','Rent amount recorded in this document',r'(?:initial rent|annual rent|yearly rent)\s*[:\-]?\s*£\s*[\d,]+(?:\.\d{2})?|£[\d,]+(?:\.\d{2})?\)?\s+per annum','Confirm which letting and period this amount applies to; do not assume it is the current rent.'),
    ('expiry','Lease term recorded',r'\b(?:\d+|five|ten|fifteen|twenty) years (?:from|commencing).{0,60}?\b20\d{2}\b','Check the operative lease, contractual end date, breaks and current occupation.'),
   ]:
    m=re.search(pattern,text,re.I)
    if m:
     ev=evidence(d,page,m,85)
     summary=norm(m.group(0))
     if title=='Rent amount recorded in this document':summary=summary.replace(') per annum',' per annum')
     if title=='Lease term recorded' and page.get('ocr'):
      summary=re.match(r'(?:\d+|five|ten|fifteen|twenty) years',summary,re.I).group(0)+' stated. The scanned commencement/expiry wording needs visual confirmation.'
     add(topic,title,summary,action,ev,'INFORMATION',True)
 # Narrow observations: separate contractual rent and concessions from rent received.
 for d in docs:
  for page in document_pages(d):
   text=norm(page['text'])
   rules=[]
   if d.doc_type.value=='lease':rules=[
    ('tenant','Tenant named in the lease',r'\(2\)\s*([A-Z][A-Z ()&.,’\'-]+?LIMITED)\s*\(registered',lambda m:'The lease names '+m.group(1)+'. Verify current occupation and any assignment.', 'Confirm the current legal tenant and covenant; a historic lease party is not necessarily today’s tenant.'),
    ('rent','Concessionary rent period',r'Concessionary Rent\s+(.{1,90}?)\s+Concessionary Rent Period\s+(.{1,180}?Term Commencement Date)',lambda m:'Concessionary rent: '+m.group(1)+'. Period: '+m.group(2)+'.', 'Confirm when this concession ended and reconcile the currently payable rent with the payment ledger.'),
   ]
   if d.doc_type.value=='epc':rules=[
    ('epc','Energy rating in the certificate',r"property.{0,8}energy rating is\s*([A-G][+]?)\b",lambda m:'The certificate text records energy rating '+m.group(1).upper()+'.', 'Confirm the certificate extent, date and rating against the original.'),
    ('epc','Certificate expiry recorded',r'Valid until:\s*(\d{1,2}\s+[A-Za-z]+\s+20\d{2})',lambda m:'Valid until '+m.group(1)+'.', 'Check for a superseding certificate and whether the certificate covers all space being bought.'),
   ]
   for topic,title,pattern,summary,action in rules:
    m=re.search(pattern,text,re.I)
    if m:add(topic,title,summary(m),action,evidence(d,page,m,80),'INFORMATION',True)
 # Catalogue is separately labelled, never masquerading as a legal-pack finding.
 context=[]
 for key,label in [('rent','Published current annual rent'),('guide','Published guide price')]:
  value=catalogue.get(key)
  if isinstance(value,(int,float)) and value>=0:context.append({'label':label,'value':f'£{value:,.0f}','source':'Published auction particulars — not independently confirmed by the legal pack'})
 kinds={d.doc_type.value for d in docs};missing=[]
 for kind,label in [('special_conditions','Special Conditions of Sale'),('title_register','Official title register'),('title_plan','Title / transfer plan'),('lease','Occupational lease if the property is let'),('epc','EPC or evidenced exemption')]:
  if kind not in kinds:missing.append(label+' — not identified in the supplied files.')
 if not kinds.intersection({'cpse1','cpse2'}):missing.append('Commercial property enquiry replies (CPSE or equivalent) were not identified.')
 if not kinds.intersection({'arrears','tenancy_schedule'}):missing.append('A separately identified current rent/payment and arrears ledger was not supplied; a tenancy schedule in conditions does not prove payments.')
 by_topic={key:[f for f in findings if f['topic']==key] for key,_,_,_ in TOPICS}
 uncertainties=[]
 leases=[d for d in docs if d.doc_type.value=='lease']
 if len(leases)>1:uncertainties.append({'title':'Multiple lease documents','text':'More than one lease was supplied. Establish their dates, demises and whether any earlier lease was surrendered or varied; amounts and obligations are not automatically cumulative.','sources':[d.name for d in leases]})
 titles=[d for d in docs if d.doc_type.value=='title_register']
 if len(titles)>1:uncertainties.append({'title':'Multiple registered titles','text':'The pack includes multiple titles. They may represent different parcels or legal interests, rather than a contradiction. Reconcile all title and lease plans with the sale extent.','sources':[d.name for d in titles]})
 seller_text=' '.join(d.text for d in docs if d.doc_type.value=='special_conditions')
 proprietors=[]
 for f in findings:
  if f['title']=='Registered proprietor recorded':proprietors.append(f['summary'].split(':',1)[-1].strip())
 if proprietors and any(norm(p).lower() not in norm(seller_text).lower() for p in proprietors):
  uncertainties.append({'title':'Seller and registered proprietor need reconciliation','text':'A registered proprietor name was not matched to the sale-conditions text. This may reflect an intervening transfer or different title; it is not proof of a defect. Ask for the complete registration chain.','sources':[d.name for d in titles]})
 for key,title,_,action in TOPICS:
  if by_topic[key] or key in ('rent','breaks','ground','buyer-fees'):questions.append({'topic':title,'question':action})
 findings.sort(key=lambda f:({'CRITICAL / RED FLAG':0,'NEEDS CHECKING':1,'INFORMATION':2}[f['severity']],f['topic'],f['source']))
 counts=Counter(f['severity'] for f in findings)
 manifest=[]
 assets={a.filename:a for a in ingestion.assets}
 for d in docs:
  meta=d.metadata;asset=assets.get(d.name)
  manifest.append({'document':d.name,'type':d.doc_type.value.replace('_',' '),'sha256':d.sha256,'pages':meta.get('page_count',0),'characters':len(d.text),
      'status':asset.status if asset else 'partial','ocr_pages':meta.get('ocr_pages',[]),'unread_pages':meta.get('unread_pages',[]),'extraction':meta.get('extraction','text'),
      'visual_check':d.doc_type.value=='title_plan'})
 known={d.name for d in docs}
 for a in ingestion.assets:
  if a.filename not in known:manifest.append({'document':a.filename,'type':a.detected_type,'sha256':a.sha256,'pages':0,'characters':0,'status':a.status,'ocr_pages':[],'unread_pages':[],'message':a.message})
 issues=[{'document':i.filename,'message':i.message,'code':i.code} for i in ingestion.issues]
 sections=[{'id':key,'title':title,'items':by_topic[key],
    'empty':'No reliable clause was identified automatically. This is not confirmation that the obligation or risk is absent. '+action}
    for key,title,_,action in TOPICS]
 observations=[f for f in findings if f['fact'] and f['severity']!='CRITICAL / RED FLAG' and f['title'] in ('Contractual completion period','Deposit recorded in the sale conditions','VAT depends on TOGC conditions','Rent amount recorded in this document','Concessionary rent period','Tenant named in the lease','Energy rating in the certificate','Certificate expiry recorded')]
 return {'schema_version':VERSION,'product':'Auction Sniper — Buyer Due Diligence Report','property':property_ref,
  'report_id':hashlib.sha256((property_ref+'|'+ '|'.join(sorted(d.sha256 for d in docs))).encode()).hexdigest()[:16],
  'created_at':datetime.now(timezone.utc).isoformat(),'summary':'Resolve the highlighted contractual and evidence gaps before relying on the pack. This is an evidence review, not a buy recommendation.',
  'observations':observations,'counts':dict(counts),'context':context,'findings':findings,'sections':sections,'documents':manifest,'missing':missing,'uncertainties':uncertainties,'questions':questions,'issues':issues,
  'coverage':{'files':len(ingestion.assets),'text_documents':sum(bool(d.text.strip()) for d in docs),'pages':ingestion.total_pages,'ocr_pages':sum(len(d.metadata.get('ocr_pages',[])) for d in docs),'unread_pages':sum(len(d.metadata.get('unread_pages',[])) for d in docs)},
  'disclaimer':'This report does not constitute legal advice. Automated extraction and OCR can miss or misread facts. Confirm material wording, plans, dates, amounts and legal effects with the original documents and the purchaser’s solicitor. A missing finding is not evidence that a risk or obligation is absent.'}
