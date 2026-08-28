"""Auction Sniper Legal Pack Intelligence backend.
Provider-independent, evidence-first buyer due diligence. It analyses documents
already lawfully supplied to the application; provider acquisition is separate.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Iterable
import hashlib, re

class DocType(str,Enum):
 SPECIAL_CONDITIONS="special_conditions"; LEASE="lease"; TRANSFER="transfer"; TITLE_REGISTER="title_register"; TITLE_PLAN="title_plan"; CPSE1="cpse1"; CPSE2="cpse2"; EPC="epc"; VAT="vat"; COURT="court"; SEARCH="search"; ENVIRONMENTAL="environmental"; ASBESTOS="asbestos"; HEALTH_SAFETY="health_safety"; ARREARS="arrears"; TENANCY_SCHEDULE="tenancy_schedule"; OTHER="other"
@dataclass
class Evidence:
 document:str; document_type:str; excerpt:str=""; page:int|None=None; clause:str|None=None; confidence:float=1.0
 paragraph:int|None=None; table:int|None=None; row:int|None=None; sheet:str|None=None
 scope:str="unknown"; temporal_status:str="unspecified"; authority:str="document"
@dataclass
class Finding: key:str; label:str; value:Any; status:str="info"; significance:str=""; evidence:list[Evidence]=field(default_factory=list)
@dataclass
class PackDocument: name:str; doc_type:DocType; text:str=""; sha256:str=""; metadata:dict[str,Any]=field(default_factory=dict)
@dataclass
class DueDiligenceReport:
 property_ref:str; assessment:str="AMBER"; assessment_text:str="Important matters require resolution before bidding."; findings:dict[str,Finding]=field(default_factory=dict); conflicts:list[dict[str,Any]]=field(default_factory=list); missing:list[str]=field(default_factory=list); documents_reviewed:list[str]=field(default_factory=list); questions:list[str]=field(default_factory=list); processing:dict[str,Any]=field(default_factory=dict)
 def to_dict(self): return asdict(self)
DOC_PATTERNS={DocType.SPECIAL_CONDITIONS:("special condition",),DocType.CPSE1:("cpse 1","cpse1"),DocType.CPSE2:("cpse 2","cpse2"),DocType.EPC:("epc","energy performance"),DocType.VAT:("vat","option to tax","ott"),DocType.COURT:("court","consent order","judgment","drafting in dispute"),DocType.ASBESTOS:("asbestos",),DocType.HEALTH_SAFETY:("health & safety","health _ safety","risk assessment"),DocType.ENVIRONMENTAL:("sitesolutions","environmental"),DocType.ARREARS:("arrears","payment history"),DocType.TENANCY_SCHEDULE:("tenancy schedule",),DocType.TITLE_REGISTER:("official copy (register)","register - cym","title register"),DocType.TITLE_PLAN:("title plan",),DocType.TRANSFER:("tp1","transfer of part"),DocType.LEASE:("lease",),DocType.SEARCH:("search","land charges","water and drainage","chancel")}
def classify_document(name,text=""):
 h=(name+" "+text[:1200]).lower()
 for k,terms in DOC_PATTERNS.items():
  if any(x in h for x in terms): return k
 return DocType.OTHER
def make_document(name,text="",raw=None,metadata=None):
 b=raw if raw is not None else text.encode("utf-8","ignore"); return PackDocument(name,classify_document(name,text),text,hashlib.sha256(b).hexdigest(),metadata or {})
def _locate(metadata,needle):
 if not needle:return {}
 target=re.sub(r"\s+"," ",needle).strip().lower()
 def hit(text):return target in re.sub(r"\s+"," ",text or "").lower()
 for p in metadata.get("pages",[]):
  if hit(p.get("text","")):return {"page":p.get("page")}
 for p in metadata.get("paragraphs",[]):
  if hit(p.get("text","")):return {"paragraph":p.get("paragraph")}
 for t in metadata.get("tables",[]):
  for row in t.get("rows",[]):
   if hit(" | ".join(row.get("cells",[]))):return {"table":t.get("table"),"row":row.get("row")}
 for sh in metadata.get("sheets",[]):
  for row in sh.get("rows",[]):
   if hit(" | ".join(row.get("cells",[]))):return {"sheet":sh.get("sheet"),"row":row.get("row")}
 return {}

def _ev(d,x,clause=None,confidence=1.0,scope="unknown",temporal_status="unspecified",authority="document"):
 loc=_locate(d.metadata or {},x)
 return Evidence(d.name,d.doc_type.value,x[:700],page=loc.get("page"),clause=clause,confidence=confidence,paragraph=loc.get("paragraph"),table=loc.get("table"),row=loc.get("row"),sheet=loc.get("sheet"),scope=scope,temporal_status=temporal_status,authority=authority)
def _put(r,f):
 old=r.findings.get(f.key)
 if old and old.value!=f.value:
  r.conflicts.append({"field":f.key,"values":[old.value,f.value],"sources":[e.document for e in old.evidence+f.evidence]})
  if f.key.startswith("proposed_"): r.findings[f.key]=f
 else:r.findings[f.key]=f
def extract_document(d,r):
 t=d.text; low=t.lower()
 if d.doc_type==DocType.SPECIAL_CONDITIONS:
  if "expired on 30 april 2024" in low:_put(r,Finding("lease_expiry","Original lease expiry","30 April 2024","amber","The contractual term has expired; assess the statutory continuation and renewal position.",[_ev(d,"tenancy expired on 30 April 2024",temporal_status="historical",authority="special_conditions")]))
  if "part ii of the landlord and tenant act 1954" in low:_put(r,Finding("tenancy_status","Current tenancy position","Statutory continuation under Part II Landlord and Tenant Act 1954","amber","The tenant remains in occupation after contractual expiry.",[_ev(d,"remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954",temporal_status="current",authority="special_conditions")]))
  m=re.search(r"rent of £\s*([\d,]+)\s*per annum and a term of five years",t,re.I)
  if m:
   v=int(m.group(1).replace(",",""));_put(r,Finding("proposed_rent","Rent agreed in principle for renewal",v,"red","Principal forward-income scenario until renewal completes.",[_ev(d,m.group(0),temporal_status="proposed",authority="special_conditions")]));_put(r,Finding("proposed_term","Renewal term agreed in principle","5 years","amber","Agreed in principle, not an executed lease.",[_ev(d,m.group(0),temporal_status="proposed",authority="special_conditions")]))
  if "renewal tenancy has not yet been completed" in low:_put(r,Finding("renewal_completion","Renewal lease completed?","No","red","Purchaser is buying before completion of the new tenancy.",[_ev(d,"renewal tenancy has not yet been completed",temporal_status="current",authority="special_conditions")]))
  charges=[]
  for label,pat in (("Search costs",r"search[^£]{0,80}£\s*([\d,]+)"),("Marketing/acquisition charge",r"(?:marketing|acquisition)[^£]{0,100}£\s*([\d,]+)")):
   m=re.search(pat,t,re.I|re.S)
   if m:charges.append((label,int(m.group(1).replace(",",""))))
  if charges:_put(r,Finding("buyer_costs","Special-condition buyer costs",charges,"red","Include these in true acquisition cost and bid modelling.",[_ev(d,str(charges))]))
  if "interim rent" in low:_put(r,Finding("interim_rent","Interim-rent exposure","Buyer assumes consequences of the renewal/interim-rent position","red","Potential historic/future balancing payment or credit should be quantified before bidding.",[_ev(d,"interim rent provisions")]))
  if "seller's application" in low and "registered proprietor" in low:_put(r,Finding("seller_registration","Seller registration","Seller's application to become registered proprietor is pending","amber","Completion/registration mechanics require conveyancer review.",[_ev(d,"seller's application to become registered proprietor")]))
  if "vat is payable in addition" in low:_put(r,Finding("special_conditions_vat","Special Conditions VAT wording","VAT payable in addition to purchase price","amber","Reconcile with any CPSE statement that TOGC treatment is expected.",[_ev(d,"VAT is payable in addition to the purchase price")]))
 elif d.doc_type==DocType.LEASE:
  m=re.search(r"(?:term[^\n]{0,80})10 years[^\n]{0,80}(?:1 may 2014|01\.05\.2014)",t,re.I)
  if m:_put(r,Finding("original_term","Original lease","10 years from 1 May 2014","info","Establishes original contractual timeline.",[_ev(d,m.group(0))]))
  if "boots opticians professional services" in low:_put(r,Finding("tenant","Tenant","Boots Opticians Professional Services Ltd","positive","Named tenant under original lease.",[_ev(d,"Boots Opticians Professional Services",scope="tenant_demise",temporal_status="historical",authority="lease")]))
  if any(x in low for x in ("exterior","structure","roof")) and "landlord" in low:_put(r,Finding("repairing_structure","Repairing obligations","Landlord retains material exterior/structure/roof responsibilities under original lease","amber","Do not describe the original lease as simple whole-building tenant-direct FRI without qualification.",[_ev(d,"landlord / exterior / structure / roof repairing provisions")]))
  if "insur" in low and "landlord" in low:_put(r,Finding("insurance_structure","Insurance","Landlord insures building under original lease; recoverability subject to lease terms","info","Check final renewal lease preserves intended cost recovery.",[_ev(d,"landlord insurance provisions")]))
 elif d.doc_type in (DocType.CPSE1,DocType.CPSE2):
  if "there is no service charge" in low:_put(r,Finding("historic_service_charge","Historic service-charge position","No conventional service charge; shared service-yard costs directly recharged","info","Historic position must be reconciled with transfer terms.",[_ev(d,"There is no service charge")]))
  if "colliers are the managing agents" in low:_put(r,Finding("managing_agent","Managing agent","Colliers","info","Management disclosed in replies.",[_ev(d,"Colliers are the managing agents")]))
  if "arrears report" in low or "please see the arrears" in low:r.missing.append("Referenced rent/service-charge arrears schedule or payment history")
  if "transfer of a going concern" in low or "togc" in low:_put(r,Finding("cpse_togc","CPSE VAT position","Seller expects TOGC treatment if conditions are satisfied","amber","Compare with Special Conditions and Option to Tax evidence.",[_ev(d,"TOGC treatment expected")]))
  if "rent deposit" in low and any(x in low for x in ("none","no rent deposit","not applicable")):_put(r,Finding("rent_deposit","Rent deposit","None disclosed","info","No deposit security identified in replies.",[_ev(d,"rent deposit reply")]))
 elif d.doc_type==DocType.TRANSFER:
  if "service charge" in low:_put(r,Finding("future_service_charge","Service charge on transfer","TP1 creates ongoing service-yard cost liability; purchaser share/budget not established","amber","Obtain current budget and proposed purchaser percentage before bidding.",[_ev(d,"TP1 service charge provisions")]))
  if any(x in low for x in ("right of way","rights of way","service media","support and shelter")):_put(r,Finding("transfer_rights","Rights granted/reserved","TP1 contains access/service/support rights and reservations","amber","Conveyancer should confirm rights are sufficient for independent operation of the transferred property.",[_ev(d,"TP1 rights granted/reserved")]))
 elif d.doc_type==DocType.TITLE_REGISTER:
  if "cym146294" in low:_put(r,Finding("title","Registered title","CYM146294","info","Property is being dealt with from the wider registered title; confirm transfer-of-part plan and registration.",[_ev(d,"CYM146294")]))
  if "pending application" in low:_put(r,Finding("pending_title_applications","Land Registry","Pending application(s) recorded","amber","Conveyancer should identify and assess pending applications before bidding.",[_ev(d,"pending applications")]))
 elif d.doc_type==DocType.VAT:
  if "option to tax" in low or "opted to tax" in low:_put(r,Finding("option_to_tax","Option to Tax","Evidence present","amber","Reconcile final VAT/TOGC completion treatment.",[_ev(d,"Option to Tax evidence")]))
 elif d.doc_type==DocType.EPC:
  m=re.search(r"(?:rating|energy rating)[^A-G]{0,30}([A-G])[^\d]{0,20}(\d{1,3})",t,re.I)
  if m:_put(r,Finding("epc","EPC",f"{m.group(1).upper()} ({m.group(2)})","positive","Captured from certificate; do not infer missing ratings.",[_ev(d,m.group(0),scope="subject_property",temporal_status="current",authority="epc_certificate")]))
 elif d.doc_type==DocType.COURT:_put(r,Finding("court_documents","Lease-renewal/court documents","Present","amber","Review chronology and unresolved drafting; presence is not evidence of tenant default.",[_ev(d,d.name)]))
 elif d.doc_type==DocType.ASBESTOS:
  sig="Differentiate tenant-demise ACM management from any landlord structural cause."
  if "water ingress" in low:sig+=" Water ingress is mentioned and should be traced to the responsible repairing party."
  _put(r,Finding("asbestos","Asbestos documentation","ACMs documented","amber",sig,[_ev(d,d.name)]))
 elif d.doc_type==DocType.ENVIRONMENTAL:
  if "surface water" in low and "moderate" in low:_put(r,Finding("surface_water","Surface-water flood risk","Moderate","amber","Review drainage/flood guidance and insurance implications.",[_ev(d,"Surface water flood risk: Moderate")]))
  if "contaminated land" in low and "pass" in low:_put(r,Finding("contaminated_land","Contaminated land","Passed","positive","No contaminated-land liability identified by this search, subject to search scope.",[_ev(d,"Contaminated land: Passed")]))
EXPECTED={DocType.SPECIAL_CONDITIONS:"Special Conditions of Sale",DocType.LEASE:"Lease",DocType.TRANSFER:"TP1/TR1 transfer",DocType.TITLE_REGISTER:"Official title register",DocType.CPSE1:"CPSE1 replies",DocType.CPSE2:"CPSE2 replies",DocType.EPC:"EPC"}
def analyse_pack(property_ref,documents:Iterable[PackDocument],catalogue=None):
 docs=list(documents);r=DueDiligenceReport(property_ref=property_ref,documents_reviewed=[d.name for d in docs]);catalogue=catalogue or {}
 for d in docs:extract_document(d,r)
 kinds={d.doc_type for d in docs}
 for k,label in EXPECTED.items():
  if k not in kinds:r.missing.append(label)
 passing=catalogue.get("rent");guide=catalogue.get("guide")
 if passing is not None:_put(r,Finding("current_rent","Current/catalogue rent",passing,"info","Current income; compare with renewal/proposed rent.",[]))
 proposed=r.findings.get("proposed_rent")
 if guide and passing:_put(r,Finding("current_giy","Gross yield on current rent",round(passing/guide*100,2),"info","Headline yield based on current rent.",[]))
 if guide and proposed:_put(r,Finding("forward_giy","Gross yield on proposed renewal rent",round(proposed.value/guide*100,2),"red","Forward-income sensitivity while renewal remains incomplete.",proposed.evidence))
 if proposed and passing and proposed.value<passing:
  drop=passing-proposed.value;_put(r,Finding("income_change","Forward rent change",{"from":passing,"to":proposed.value,"drop":drop,"drop_pct":round(drop/passing*100,1)},"red","Material reduction between current income and renewal terms agreed in principle.",proposed.evidence));r.assessment="AMBER";r.assessment_text="Attractive income profile, but important matters require resolution before bidding. The principal issue is the material reduction between current rent and the renewal terms agreed in principle."
 if r.findings.get("historic_service_charge") and r.findings.get("future_service_charge"):r.conflicts.append({"field":"service_charge_position","values":["historic: no conventional service charge","future: TP1 service-yard liability"],"sources":[r.findings["historic_service_charge"].evidence[0].document,r.findings["future_service_charge"].evidence[0].document]})
 if r.findings.get("cpse_togc") and r.findings.get("special_conditions_vat"):r.conflicts.append({"field":"vat_treatment","values":[r.findings["cpse_togc"].value,r.findings["special_conditions_vat"].value],"sources":[r.findings["cpse_togc"].evidence[0].document,r.findings["special_conditions_vat"].evidence[0].document]})
 q=[]
 if any("arrears" in x.lower() for x in r.missing):q.append("Obtain and review the referenced rent/service-charge arrears schedule and payment history.")
 if r.findings.get("future_service_charge"):q.append("Obtain the current service-yard budget and the purchaser's proposed percentage/share under the TP1.")
 if r.findings.get("renewal_completion"):q.append("Confirm final Boots renewal lease terms, execution status, court timetable and interim-rent exposure before bidding.")
 if r.findings.get("cpse_togc") or r.findings.get("special_conditions_vat"):q.append("Confirm with the conveyancer/accountant whether completion is intended as TOGC and the cash VAT position if TOGC conditions fail.")
 if r.findings.get("seller_registration"):q.append("Confirm the seller's pending registration and the mechanics/timing for the buyer's transfer-of-part registration.")
 r.questions=q;r.missing=list(dict.fromkeys(r.missing));r.processing={"documents":len(docs),"schema_version":"1.1","provider_independent":True};return r
