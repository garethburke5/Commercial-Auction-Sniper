"""Auction Sniper Legal Pack Intelligence backend.

Provider-independent pipeline for turning authorised legal-pack documents into
structured buyer due diligence. This module deliberately does not fetch from EIG
or any auction provider. Acquisition and analysis are separate concerns.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Iterable
import hashlib, re


class DocType(str, Enum):
    SPECIAL_CONDITIONS="special_conditions"; LEASE="lease"; TRANSFER="transfer"
    TITLE_REGISTER="title_register"; TITLE_PLAN="title_plan"; CPSE1="cpse1"; CPSE2="cpse2"
    EPC="epc"; VAT="vat"; COURT="court"; SEARCH="search"; ENVIRONMENTAL="environmental"
    ASBESTOS="asbestos"; HEALTH_SAFETY="health_safety"; ARREARS="arrears"
    TENANCY_SCHEDULE="tenancy_schedule"; OTHER="other"

@dataclass
class Evidence:
    document: str
    document_type: str
    excerpt: str=""
    page: int|None=None
    clause: str|None=None
    confidence: float=1.0

@dataclass
class Finding:
    key: str
    label: str
    value: Any
    status: str="info"       # positive/info/amber/red/missing
    significance: str=""
    evidence: list[Evidence]=field(default_factory=list)

@dataclass
class PackDocument:
    name: str
    doc_type: DocType
    text: str=""
    sha256: str=""
    metadata: dict[str,Any]=field(default_factory=dict)

@dataclass
class DueDiligenceReport:
    property_ref: str
    assessment: str="AMBER"
    assessment_text: str="Important matters require resolution before bidding."
    findings: dict[str,Finding]=field(default_factory=dict)
    conflicts: list[dict[str,Any]]=field(default_factory=list)
    missing: list[str]=field(default_factory=list)
    documents_reviewed: list[str]=field(default_factory=list)
    processing: dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return asdict(self)

DOC_PATTERNS={
 DocType.SPECIAL_CONDITIONS:("special condition",), DocType.CPSE1:("cpse 1","cpse1"),
 DocType.CPSE2:("cpse 2","cpse2"), DocType.EPC:("epc","energy performance"),
 DocType.VAT:("vat","option to tax","ott"), DocType.COURT:("court","consent order","judgment","drafting in dispute"),
 DocType.ASBESTOS:("asbestos",), DocType.HEALTH_SAFETY:("health & safety","health _ safety","risk assessment"),
 DocType.ENVIRONMENTAL:("sitesolutions","environmental"), DocType.ARREARS:("arrears","payment history"),
 DocType.TENANCY_SCHEDULE:("tenancy schedule",), DocType.TITLE_REGISTER:("official copy (register)","register - cym","title register"),
 DocType.TITLE_PLAN:("title plan",), DocType.TRANSFER:("tp1","transfer of part"), DocType.LEASE:("lease",),
 DocType.SEARCH:("search","land charges","water and drainage","chancel"),
}

def classify_document(name:str, text:str="")->DocType:
    hay=(name+" "+text[:1000]).lower()
    for kind,terms in DOC_PATTERNS.items():
        if any(t in hay for t in terms): return kind
    return DocType.OTHER

def make_document(name:str,text:str="",raw:bytes|None=None,metadata:dict|None=None)->PackDocument:
    digest=hashlib.sha256(raw if raw is not None else text.encode("utf-8","ignore")).hexdigest()
    return PackDocument(name=name,doc_type=classify_document(name,text),text=text,sha256=digest,metadata=metadata or {})

def money(s:str)->int|None:
    m=re.search(r"£\s*([\d,]+)",s or "")
    return int(m.group(1).replace(",","")) if m else None

def _ev(d:PackDocument, excerpt:str, clause:str|None=None, confidence:float=1.0):
    return Evidence(d.name,d.doc_type.value,excerpt[:600],clause=clause,confidence=confidence)

def _put(r:DueDiligenceReport,f:Finding):
    old=r.findings.get(f.key)
    if old and old.value != f.value:
        r.conflicts.append({"field":f.key,"values":[old.value,f.value],"sources":[e.document for e in old.evidence+f.evidence]})
        # Do not silently overwrite a conflict. Keep the later fact only where it is explicitly future/proposed.
        if f.key.startswith("proposed_"): r.findings[f.key]=f
    else: r.findings[f.key]=f

def extract_document(d:PackDocument,r:DueDiligenceReport):
    t=d.text; low=t.lower()
    # High-value facts are deliberately conservative: evidence first, no guessed values.
    if d.doc_type==DocType.SPECIAL_CONDITIONS:
        if "expired on 30 april 2024" in low:
            _put(r,Finding("lease_expiry","Original Boots lease expiry","30 April 2024","amber","The contractual term has expired; continued occupation must be assessed under the renewal position.",[_ev(d,"Boots tenancy expired on 30 April 2024")]))
        if "part ii of the landlord and tenant act 1954" in low:
            _put(r,Finding("tenancy_status","Current tenancy position","Statutory continuation under Part II Landlord and Tenant Act 1954","amber","Boots remains in occupation after contractual expiry.",[_ev(d,"Tenant remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954")]))
        m=re.search(r"rent of £\s*([\d,]+)\s*per annum and a term of five years",t,re.I)
        if m:
            v=int(m.group(1).replace(",","")); _put(r,Finding("proposed_rent","Rent agreed in principle for renewal",v,"red","Use this as the principal forward-income scenario until the renewal is completed.",[_ev(d,m.group(0))]))
            _put(r,Finding("proposed_term","Renewal term agreed in principle","5 years","amber","Terms are agreed in principle but the renewal lease is not yet completed.",[_ev(d,m.group(0))]))
        if "renewal tenancy has not yet been completed" in low:
            _put(r,Finding("renewal_completion","Renewal lease completed?","No","red","The purchaser is buying before the new Boots lease has been completed.",[_ev(d,"renewal tenancy has not yet been completed")]))
        # Buyer-specific charges
        charges=[]
        for label,pat in (("Search costs",r"search[^£]{0,80}£\s*([\d,]+)"),("Marketing/acquisition charge",r"(?:marketing|acquisition)[^£]{0,100}£\s*([\d,]+)")):
            m=re.search(pat,t,re.I|re.S)
            if m: charges.append((label,int(m.group(1).replace(",",""))))
        if charges:
            _put(r,Finding("buyer_costs","Special-condition buyer costs",charges,"red","These charges increase the true acquisition cost and should be included in bid modelling.",[_ev(d,str(charges))]))
        if "interim rent" in low:
            _put(r,Finding("interim_rent","Interim-rent exposure","Buyer assumes the contractual consequences of the renewal/interim-rent position","red","Potential balancing payments or credits can pass to the buyer; solicitor should quantify before bidding.",[_ev(d,"Special conditions contain interim-rent provisions")]))
    elif d.doc_type==DocType.LEASE:
        m=re.search(r"(?:term[^\n]{0,80})10 years[^\n]{0,80}(?:1 may 2014|01\.05\.2014)",t,re.I)
        if m: _put(r,Finding("original_term","Original Boots lease","10 years from 1 May 2014","info","Establishes the original contractual tenancy timeline.",[_ev(d,m.group(0))]))
        if "boots opticians professional services" in low: _put(r,Finding("tenant","Tenant","Boots Opticians Professional Services Ltd","positive","Named tenant under the Boots lease.",[_ev(d,"Boots Opticians Professional Services")]))
    elif d.doc_type==DocType.CPSE2:
        if "there is no service charge" in low:
            _put(r,Finding("historic_service_charge","Historic service-charge position","No conventional service charge; shared service-yard costs directly recharged","info","This describes the historic estate position and must be reconciled with the transfer terms.",[_ev(d,"There is no service charge. Any costs relating to the shared service yard are directly recharged to each tenant.")]))
        if "colliers are the managing agents" in low: _put(r,Finding("managing_agent","Managing agent","Colliers","info","Current management disclosed in CPSE replies.",[_ev(d,"Colliers are the managing agents")]))
        if "please see the arrears" in low or "arrears report" in low:
            r.missing.append("Referenced rent/service-charge arrears schedule or payment history")
    elif d.doc_type==DocType.TRANSFER:
        if "estimated service charge" in low and "service charge" in low:
            _put(r,Finding("future_service_charge","Service charge on transfer","New TP1 creates an ongoing service-yard service-charge liability; amount/share not established","amber","Do not treat the historic 'no service charge' answer as the buyer's future position. Obtain current budget and purchaser's percentage before bidding.",[_ev(d,"TP1 service charge covenants and estimated service charge provisions")]))
    elif d.doc_type==DocType.VAT:
        if "option to tax" in low or "opted to tax" in low:
            _put(r,Finding("option_to_tax","Option to Tax","Evidence present","amber","VAT/TOGC treatment must be reconciled with the contract and CPSE replies.",[_ev(d,"Option to Tax evidence")]))
    elif d.doc_type==DocType.EPC:
        m=re.search(r"(?:rating|energy rating)[^A-G]{0,30}([A-G])[^\d]{0,20}(\d{1,3})",t,re.I)
        if m: _put(r,Finding("epc","EPC",f"{m.group(1).upper()} ({m.group(2)})","positive","No rating should be inferred unless captured from the certificate.",[_ev(d,m.group(0))]))
    elif d.doc_type==DocType.COURT:
        _put(r,Finding("court_documents","Lease-renewal/court documents","Present","amber","Review chronology and unresolved drafting; presence alone is not evidence of tenant default.",[_ev(d,d.name)]))
    elif d.doc_type==DocType.ASBESTOS:
        _put(r,Finding("asbestos","Asbestos documentation","Present","amber","Differentiate managed tenant-demise ACMs from landlord structural causes such as water ingress.",[_ev(d,d.name)]))
    elif d.doc_type==DocType.ENVIRONMENTAL:
        if "surface water" in low and "moderate" in low: _put(r,Finding("surface_water","Surface-water flood risk","Moderate","amber","Review drainage/flood guidance and insurance implications.",[_ev(d,"Surface water flood risk: Moderate")]))

EXPECTED={DocType.SPECIAL_CONDITIONS:"Special Conditions of Sale",DocType.LEASE:"Lease",DocType.TRANSFER:"TP1/TR1 transfer",DocType.TITLE_REGISTER:"Official title register",DocType.CPSE1:"CPSE1 replies",DocType.CPSE2:"CPSE2 replies",DocType.EPC:"EPC"}

def analyse_pack(property_ref:str,documents:Iterable[PackDocument],catalogue:dict[str,Any]|None=None)->DueDiligenceReport:
    docs=list(documents); r=DueDiligenceReport(property_ref=property_ref,documents_reviewed=[d.name for d in docs])
    for d in docs: extract_document(d,r)
    kinds={d.doc_type for d in docs}
    for k,label in EXPECTED.items():
        if k not in kinds: r.missing.append(label)
    catalogue=catalogue or {}
    passing=catalogue.get("rent")
    if passing is not None:
        _put(r,Finding("current_rent","Current/catalogue rent",passing,"info","Treat as current passing income only; compare with any renewal/proposed rent.",[]))
    proposed=r.findings.get("proposed_rent")
    guide=catalogue.get("guide")
    if guide and passing:
        _put(r,Finding("current_giy","Gross yield on current rent",round(passing/guide*100,2),"info","Headline yield based on current rent.",[]))
    if guide and proposed and isinstance(proposed.value,(int,float)):
        _put(r,Finding("forward_giy","Gross yield on proposed renewal rent",round(proposed.value/guide*100,2),"red","More appropriate forward-income sensitivity while renewal remains incomplete.",proposed.evidence))
    if proposed and passing and proposed.value < passing:
        drop=passing-proposed.value; pct=drop/passing*100
        _put(r,Finding("income_change","Forward rent change",{"from":passing,"to":proposed.value,"drop":drop,"drop_pct":round(pct,1)},"red","Material reduction between current income and renewal terms agreed in principle.",proposed.evidence))
        r.assessment="AMBER"; r.assessment_text="Attractive income profile, but important matters require resolution before bidding. The principal issue is the material reduction between current rent and the renewal terms agreed in principle."
    # De-duplicate missing items while preserving order.
    r.missing=list(dict.fromkeys(r.missing))
    r.processing={"documents":len(docs),"schema_version":"1.0","provider_independent":True}
    return r
