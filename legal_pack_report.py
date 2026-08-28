"""Professional-English report assembly for Auction Sniper Legal Pack Intelligence.
Consumes structured findings; it does not re-interpret raw legal documents.
"""
from __future__ import annotations
from typing import Any

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
