"""Professional-English report assembly for Auction Sniper Legal Pack Intelligence.
Consumes structured findings; it does not re-interpret raw legal documents.
"""
from __future__ import annotations
from typing import Any
from html import escape
import json,re

def _money(v): return f"£{v:,.0f}" if isinstance(v,(int,float)) else str(v)
def _source(f):
 docs=[]
 for e in getattr(f,"evidence",[]):
  if e.document not in docs:docs.append(e.document)
 return "; ".join(docs) if docs else "Auction particulars / catalogue data"
def _display(f):
 v=f.value
 if f.key.endswith("giy") and isinstance(v,(int,float)):return f"{v:.2f}%"
 if f.key in ("current_rent","proposed_rent") and isinstance(v,(int,float)):return _money(v)+" p.a."
 if f.key=="income_change" and isinstance(v,dict):return f"{_money(v['from'])} → {_money(v['to'])} p.a. ({v['drop_pct']:.1f}% reduction)"
 if f.key=="buyer_costs" and isinstance(v,list):return "; ".join(f"{a}: {_money(b)}" for a,b in v)
 return str(v)
def _entry(f):return {"key":f.key,"label":f.label,"value":f.value,"display_value":_display(f),"status":f.status,"significance":f.significance,"source":_source(f),"evidence":[{"document":e.document,"excerpt":e.excerpt,"page":e.page,"clause":e.clause} for e in f.evidence]}
def build_report(report,catalogue:dict[str,Any]|None=None)->dict[str,Any]:
 catalogue=catalogue or {};f=report.findings;sections=[];current=f.get("current_rent");proposed=f.get("proposed_rent");expiry=f.get("lease_expiry");paras=[]
 if current and proposed:paras.append(f"The property is currently presented with income of {_money(current.value)} per annum. However, the material forward-looking figure is {_money(proposed.value)} per annum: the rent recorded as agreed in principle for the proposed renewal tenancy. The investment should therefore be assessed principally against the proposed renewal rent rather than the headline current income.")
 if expiry:
  txt=f"The original lease expired on {expiry.value}."
  if f.get("tenancy_status"):txt+=" The tenant has not vacated and remains in occupation under the statutory continuation and renewal position recorded in the legal pack."
  paras.append(txt)
 if f.get("proposed_term"):paras.append(f"The legal pack records that the parties have agreed in principle a new {f['proposed_term'].value} tenancy. The renewal lease is not yet completed, so these terms should not be treated as an executed lease until confirmed by the purchaser's solicitor.")
 sections.append({"title":"Investment Assessment","rating":report.assessment,"summary":report.assessment_text,"paragraphs":paras,"sources":sorted({_source(x) for x in (current,proposed,expiry) if x})})
 income=[_entry(f[k]) for k in ("current_rent","proposed_rent","income_change","current_giy","forward_giy","buyer_costs") if k in f];sections.append({"title":"Income, Yield & Acquisition Costs","items":income})
 groups=[("Tenant & Lease",("tenant","original_term","lease_expiry","tenancy_status","proposed_term","renewal_completion","interim_rent","court_documents")),("Repairing & Insurance Obligations",("repairing_structure","insurance_structure")),("Service Charge",("historic_service_charge","future_service_charge","managing_agent")),("Title, Registration & Rights",("title","pending_title_applications","seller_registration","transfer_rights")),("VAT & TOGC",("option_to_tax","cpse_togc","special_conditions_vat")),("Property & Environmental Matters",("epc","asbestos","surface_water","contaminated_land")),("Security, Arrears & Guarantees",("rent_deposit",))]
 for title,keys in groups:
  items=[_entry(f[k]) for k in keys if k in f]
  if items:sections.append({"title":title,"items":items})
 if report.conflicts:sections.append({"title":"Matters Requiring Reconciliation","rating":"AMBER","items":report.conflicts})
 if report.missing:sections.append({"title":"Missing or Unverified Information","rating":"AMBER","items":[{"item":x,"action":"Obtain and review before relying on the relevant conclusion."} for x in report.missing]})
 if report.questions:sections.append({"title":"Questions to Resolve Before Bidding","items":[{"question":x} for x in report.questions]})
 sections.append({"title":"Documents Reviewed","items":[{"document":x} for x in report.documents_reviewed]})
 return {"product":"Auction Sniper — Buyer Due Diligence Report","property":report.property_ref,"guide":catalogue.get("guide"),"assessment":report.assessment,"sections":sections,"disclaimer":"This report is an investment due-diligence aid. It summarises and cross-checks information identified in the supplied documents and does not constitute legal advice or replace review by the purchaser's solicitor, surveyor, accountant or other professional adviser.","processing":report.processing}
def render_text(model:dict[str,Any])->str:
 out=[model["product"],model["property"],f"Overall assessment: {model['assessment']}",""]
 for s in model["sections"]:
  out.append(s["title"].upper())
  if s.get("summary"):out.append(s["summary"])
  out.extend(s.get("paragraphs",[]))
  for item in s.get("items",[]):
   if "label" in item:out.append(f"{item['label']}: {item['display_value']} — {item.get('significance','')} Source: {item.get('source','')}")
   elif "question" in item:out.append(f"• {item['question']}")
   elif "document" in item:out.append(f"• {item['document']}")
   elif "item" in item:out.append(f"• {item['item']} — {item.get('action','')}")
   else:out.append(f"• {item}")
  out.append("")
 out.extend(["IMPORTANT",model["disclaimer"]]);return "\n".join(out)


REVIEW_CSS='''
.dd-report{font:16px/1.65 Inter,Arial,sans-serif;color:#183149;background:#fff;border:1px solid #d8e1e9;border-radius:12px;padding:28px;max-width:1120px;margin:auto;overflow-wrap:anywhere;color-scheme:light}
.dd-report *{box-sizing:border-box}.dd-report h1,.dd-report h2,.dd-report h3,.dd-report p,.dd-report summary,.dd-report li,.dd-report td,.dd-report th,.dd-report blockquote,.dd-report dt,.dd-report dd{color:#183149}
.dd-report h1{font-size:1.8rem;line-height:1.25;margin:12px 0}.dd-report h2{font-size:1.3rem;margin:30px 0 14px}.dd-report h3{font-size:1.03rem;margin:8px 0}.dd-report p{margin:9px 0}.dd-report a{color:#00665f;text-decoration:underline;text-underline-offset:3px}.dd-report .dd-kicker{font-size:.72rem;font-weight:800;letter-spacing:.12em;color:#00665f}.dd-report .dd-muted{color:#526475;font-size:.85rem}
.dd-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:20px 0}.dd-stat{background:#f1f5f8;border:1px solid #d7e1ea;border-radius:8px;padding:14px}.dd-stat b{display:block;font-size:1.5rem}.dd-stat span{font-size:.8rem;color:#425a6e}.dd-callout{background:#fff7e7;border-left:4px solid #956000;padding:14px 18px;border-radius:5px}.dd-nav{display:flex;flex-wrap:wrap;gap:10px 18px;border-block:1px solid #d7e1ea;padding:14px 0;margin:22px 0}.dd-nav a{font-size:.86rem}
.dd-finding{margin:14px 0;padding:18px;border:1px solid #d5e0e8;border-left:4px solid #327f86;border-radius:7px;background:#fff}.dd-finding.critical{border-left-color:#ac2727;background:#fff8f7}.dd-finding.check{border-left-color:#a06900;background:#fffdf7}.dd-badge{display:inline-block;font-size:.67rem;font-weight:800;letter-spacing:.05em;border-radius:4px;padding:4px 7px;background:#e6f1f1;color:#125057}.dd-finding.critical .dd-badge{background:#fbe2dd;color:#862020}.dd-finding.check .dd-badge{background:#f8edcf;color:#745000}
.dd-report details{margin:12px 0}.dd-report summary{cursor:pointer;font-weight:700;padding:10px 0}.dd-topic{border:1px solid #d6e0e8;border-radius:8px;padding:8px 18px;background:#fff;scroll-margin-top:20px}.dd-topic>summary{font-size:1rem}.dd-report blockquote{margin:12px 0 0;padding:14px 16px;border-left:3px solid #9aadb9;background:#f1f5f8;font-size:.9rem;white-space:normal}.dd-source{font-size:.8rem;color:#425a6e!important}.dd-report ul{padding-left:22px}.dd-report li{margin:9px 0}.dd-doc{border-bottom:1px solid #dce4ec;padding:12px 0}.dd-doc h3{font-size:.9rem}.dd-doc code{font-size:.7rem;color:#43596c}.dd-report .dd-action{font-weight:550}.dd-report section{scroll-margin-top:20px}.dd-report footer{display:block;border-top:1px solid #cbd8e2;padding-top:20px;margin-top:30px;font-size:.85rem}.dd-report .dd-context{display:flex;gap:15px;flex-wrap:wrap}.dd-context div{padding:12px 16px;background:#edf5f3;border-radius:6px}.dd-context strong{display:block}
@media(max-width:650px){.dd-report{padding:17px;font-size:15px;border-radius:6px}.dd-report h1{font-size:1.4rem}.dd-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.dd-finding{padding:14px}.dd-topic{padding:7px 13px}.dd-nav{gap:8px 14px}}
@media print{body{background:white}.dd-report{border:0;padding:0;max-width:none;font-size:10pt}.dd-report details{display:block}.dd-report details>*{display:block!important}.dd-report summary{display:block}.dd-finding,.dd-doc{break-inside:avoid}.dd-nav,.dd-print{display:none}.dd-report a{color:#183149;text-decoration:none}}
'''

def validate_saved_review(raw):
 if len(raw)>8*1024*1024:raise ValueError('Saved report exceeds the 8 MB limit.')
 try:model=json.loads(raw)
 except (ValueError,UnicodeError) as exc:raise ValueError('Choose an Auction Sniper JSON report.') from exc
 if not isinstance(model,dict) or model.get('schema_version')!='2.0':raise ValueError('This is not a supported Auction Sniper report.')
 if not re.fullmatch(r'[a-f0-9]{16}',str(model.get('report_id',''))):raise ValueError('Invalid report identifier.')
 for k in ('property','report_id','created_at','summary','disclaimer'):
  if not isinstance(model.get(k),str) or len(model[k])>5000:raise ValueError('Invalid report content.')
 for k in ('findings','sections','documents','questions','missing','uncertainties','issues','context'):
  if not isinstance(model.get(k),list) or len(model[k])>2000:raise ValueError('Invalid report sections.')
 if not isinstance(model.get('coverage'),dict) or not isinstance(model.get('counts'),dict):raise ValueError('Invalid report coverage.')
 for f in model['findings']:
  if not isinstance(f,dict) or f.get('severity') not in ('CRITICAL / RED FLAG','NEEDS CHECKING','INFORMATION'):raise ValueError('Invalid finding severity.')
  if not isinstance(f.get('evidence'),list):raise ValueError('Invalid finding evidence.')
 try:render_review_html(model,standalone=True)
 except (KeyError,TypeError,ValueError,AttributeError) as exc:raise ValueError('The saved report is incomplete or malformed.') from exc
 return model


def render_review_text(model):
 lines=[model['product'],model['property'],'EXECUTIVE SUMMARY',model['summary'],model['disclaimer'],'']
 for section in model['sections']:
  lines.append(section['title'].upper())
  for f in section['items']:
   lines.extend([f["severity"]+' — '+f['title'],f['summary'],'Action: '+f['action']])
   for e in f['evidence']:lines.extend([f"Source: {e['document']} · page {e.get('page') or 'not paginated'}"+(' · OCR' if e.get('ocr') else ''),e['excerpt']])
  if not section['items']:lines.append(section['empty'])
  lines.append('')
 lines.extend(['MISSING DOCUMENTS / EVIDENCE',*model['missing'],'','QUESTIONS FOR YOUR SOLICITOR'])
 lines.extend(q['question'] for q in model['questions'])
 return '\n'.join(lines)


def render_review_html(model,standalone=False):
 """Escaped HTML shared by Streamlit and the portable, offline report."""
 esc=lambda x:escape(str(x if x is not None else ''),quote=True)
 def finding(f):
  cls={'CRITICAL / RED FLAG':'critical','NEEDS CHECKING':'check','INFORMATION':'information'}[f['severity']]
  sources=[]
  for e in f['evidence']:
   location=f" · PDF page {e['page']}" if e.get('page') else ''
   sources.append('<p class="dd-source">'+esc(e['document']+location+(' · OCR: verify against the scan' if e.get('ocr') else ''))+'</p><blockquote>'+esc(e['excerpt'])+'</blockquote>')
  return '<article class="dd-finding '+cls+'"><span class="dd-badge">'+esc(f['severity'])+'</span><h3>'+esc(f['title'])+'</h3><p>'+esc(f['summary'])+'</p><p class="dd-action"><b>Action:</b> '+esc(f['action'])+'</p><details><summary>Source evidence</summary>'+''.join(sources)+'</details></article>'
 cov=model['coverage'];out=['<style>'+REVIEW_CSS+'</style><article class="dd-report">',
  '<p class="dd-kicker">AUCTION SNIPER / BUYER DUE DILIGENCE</p><h1>'+esc(model['property'])+'</h1>',
  '<p class="dd-muted">Report '+esc(model['report_id'])+' · '+esc(model['created_at'][:10])+' · Evidence review v2</p>',
  '<section id="dd-executive"><h2>Executive summary</h2><p>'+esc(model['summary'])+'</p></section><div class="dd-stats">']
 for n,label in [(cov.get('uploaded_files',cov['files']),'files supplied'),(cov['pages'],'pages processed'),(cov['ocr_pages'],'pages read with OCR'),(cov['unread_pages'],'pages needing visual review')]:out.append('<div class="dd-stat"><b>'+esc(n)+'</b><span>'+label+'</span></div>')
 out.append('</div><p class="dd-callout">'+esc(model['disclaimer'])+'</p>')
 if model['context']:
  out.append('<div class="dd-context">')
  for c in model['context']:out.append('<div>'+esc(c['label'])+'<strong>'+esc(c['value'])+'</strong><small>'+esc(c['source'])+'</small></div>')
  out.append('</div>')
 out.append('<nav class="dd-nav" aria-label="Report sections"><a href="#dd-critical">Critical risks</a><a href="#dd-checks">Solicitor checks</a><a href="#dd-detail">Detailed findings</a><a href="#dd-gaps">Gaps & uncertainties</a><a href="#dd-questions">Questions</a><a href="#dd-documents">Documents</a></nav>')
 critical=[f for f in model['findings'] if f['severity']=='CRITICAL / RED FLAG']
 out.append('<section id="dd-critical"><h2>Critical risks / red flags</h2>')
 out.extend(finding(f) for f in critical)
 if not critical:out.append('<p>No critical clause was identified automatically. This is not a clean bill of health; review the evidence gaps and obtain professional advice.</p>')
 out.append('</section><section id="dd-checks"><h2>Matters requiring solicitor verification</h2><ul>')
 checks=[]
 for f in model['findings']:
  if f['severity']=='NEEDS CHECKING' and f['action'] not in checks:checks.append(f['action'])
 for action in checks[:8]:out.append('<li>'+esc(action)+'</li>')
 out.append('</ul><p class="dd-muted">The complete topic checks and supporting extracts are below.</p></section>')
 if model.get('observations'):
  out.append('<section><h2>Key document observations</h2><p class="dd-muted">These are source-specific statements, not independent confirmation of the current position. Earlier leases and concessions are kept separate.</p><ul>')
  for f in model['observations']:
   e=f['evidence'][0];source=e['document']+(f" · PDF page {e['page']}" if e.get('page') else '')+(' · OCR: verify original' if e.get('ocr') else '')
   out.append('<li><b>'+esc(f['title'])+':</b> '+esc(f['summary'])+'<br><span class="dd-source">'+esc(source)+'</span></li>')
  out.append('</ul></section>')
 out.append('<section id="dd-detail"><h2>Detailed findings</h2>')
 for section in model['sections']:
  out.append('<details class="dd-topic" id="dd-'+esc(section['id'])+'"><summary>'+esc(section['title'])+' · '+str(len(section['items']))+' finding'+('s' if len(section['items'])!=1 else '')+'</summary>')
  if section['items']:out.extend(finding(f) for f in section['items'])
  else:out.append('<p>'+esc(section['empty'])+'</p>')
  out.append('</details>')
 out.append('</section><section id="dd-gaps"><h2>Missing documents and evidence</h2><ul>')
 out.extend('<li>'+esc(x)+'</li>' for x in model['missing'])
 if not model['missing']:out.append('<li>The expected document types were identified. Completeness and legal adequacy still require confirmation.</li>')
 out.append('</ul><h2>Contradictions / uncertainties</h2>')
 for item in model['uncertainties']:out.append('<div class="dd-finding check"><h3>'+esc(item['title'])+'</h3><p>'+esc(item['text'])+'</p><p class="dd-source">'+esc('; '.join(item['sources']))+'</p></div>')
 for issue in model['issues']:out.append('<p class="dd-callout"><b>'+esc(issue['document'])+':</b> '+esc(issue['message'])+'</p>')
 out.append('</section><section id="dd-questions"><h2>Questions to raise with your solicitor</h2><ol>')
 out.extend('<li><b>'+esc(q['topic'])+':</b> '+esc(q['question'])+'</li>' for q in model['questions'])
 out.append('</ol></section><section id="dd-documents"><h2>Document register</h2><p>Processing means extracting available text, not legally verifying every clause. Plans always require visual comparison.</p>')
 for d in model['documents']:
  status={'analysed':'Text extracted','partial':'Partial extraction — visual check needed','visual_review_required':'Visual review required','unsupported':'Not extracted','conversion_required':'Conversion required','expanded':'Archive expanded','duplicate':'Duplicate bytes — counted once'}.get(d['status'],d['status'])
  out.append('<div class="dd-doc"><h3>'+esc(d['document'])+'</h3><p>'+esc(status)+' · '+str(d['pages'])+' pages · '+str(len(d.get('ocr_pages',[])))+' OCR pages · '+esc(d['type'])+'</p>')
  if d.get('visual_check'):out.append('<p class="dd-callout">Plan: boundaries, colouring and extent must be checked visually.</p>')
  if d.get('unread_pages'):out.append('<p>Review PDF pages '+esc(', '.join(map(str,d['unread_pages'])))+' visually.</p>')
  out.append('<details><summary>Document fingerprint</summary><code>'+esc(d['sha256'])+'</code></details></div>')
 out.append('</section><footer>'+esc(model['disclaimer'])+'</footer></article>')
 html=''.join(out)
 if standalone:html='<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+esc(model['property'])+' — Auction Sniper report</title></head><body style="margin:0;padding:16px;background:#eff3f6">'+html+'</body></html>'
 return html
