"""Generic commercial property particulars extraction for Auction Sniper.

Designed to enrich every listed commercial/mixed-use lot from auction particulars
before legal-pack analysis. Evidence-first: only returns fields explicitly supported
by the supplied text and keeps source excerpts for verification.
"""
from __future__ import annotations
import re
from dataclasses import dataclass,asdict
from typing import Any

@dataclass
class ExtractedField:
    value: Any
    source_text: str
    confidence: float = 0.9

def _field(value,match,confidence=.9):
    return ExtractedField(value,match.group(0).strip() if match else "",confidence)

def _money(s):
    try:return int(float(s.replace(",","")))
    except:return None

def extract_particulars(text:str)->dict[str,dict]:
    """Extract commercially useful facts from arbitrary auction particulars text."""
    t=" ".join((text or "").replace("\xa0"," ").split())
    out={}
    # Passing/current rent: avoid historic/ERV/proposed wording.
    rent_patterns=[
      r"(?:fully let|let|producing|annual income(?: of)?|passing rent(?: of)?)[^£]{0,120}£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.a\.|pa)",
      r"£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.a\.|pa)"
    ]
    for pat in rent_patterns:
      for m in re.finditer(pat,t,re.I):
        pre=t[max(0,m.start()-80):m.start()].lower()
        if any(x in pre for x in ("previously","former rent","market rent","erv","estimated rental","proposed rent","under offer")):continue
        out["rent"]=_field(_money(m.group(1)),m,.95);break
      if "rent" in out:break
    # Tenant / covenant.
    for pat in (r"let to\s+(.{3,100}?)(?=\s+(?:on|for|at|producing|by way|under)|[.;])",r"tenant[:\s]+(.{3,100}?)(?=[.;])"):
      m=re.search(pat,t,re.I)
      if m:out["tenant"]=_field(m.group(1).strip(" ,"),m,.88);break
    # Lease term, commencement and expiry. Keep distinct values.
    m=re.search(r"(?:lease|tenancy)[^.;]{0,140}?(?:for a term of|term of)\s*(\d{1,3})\s*years",t,re.I)
    if not m:m=re.search(r"(\d{1,3})\s*year\s+(?:fri\s+)?lease",t,re.I)
    if m:out["lease_term_years"]=_field(int(m.group(1)),m,.95)
    date=r"(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|[A-Za-z]+\s+\d{4})"
    m=re.search(r"(?:commenc(?:ing|ed|ement)|from)\s+"+date,t,re.I)
    if m:out["lease_start"]=_field(m.group(1),m,.9)
    m=re.search(r"(?:expir(?:y|es|ing)|until|to)\s+"+date,t,re.I)
    if m:out["lease_expiry"]=_field(m.group(1),m,.94)
    # Break clause, including tenant-only breaks and dates.
    m=re.search(r".{0,80}(?:tenant(?:'s)?\s+)?break(?: clause| option)?[^.;]{0,180}",t,re.I)
    if m:out["break_clause"]=_field(m.group(0).strip(),m,.9)
    # Rent review.
    m=re.search(r".{0,60}rent review[^.;]{0,160}",t,re.I)
    if m:out["rent_review"]=_field(m.group(0).strip(),m,.88)
    # FRI / repairing structure.
    m=re.search(r"(?:full repairing and insuring|fully repairing and insuring|\bFRI\b)",t,re.I)
    if m:out["repairing_basis"]=_field("FRI",m,.95)
    # EPC: rating and optional numeric score.
    m=re.search(r"(?:EPC|Energy Performance Certificate|energy rating)[^A-G0-9]{0,50}([A-G])(?:\s*\(?\s*(\d{1,3})\s*\)?)?",t,re.I)
    if m:
      val=m.group(1).upper()+(f" ({m.group(2)})" if m.group(2) else "")
      out["epc"]=_field(val,m,.93)
    # Floor area.
    vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square feet)",t,re.I):
      try:vals.append((float(m.group(1).replace(",","")),m))
      except:pass
    if vals:
      v,m=max(vals,key=lambda x:x[0]);out["area_sqft"]=_field(int(round(v)),m,.85)
    vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|square metres?)",t,re.I):
      try:vals.append((float(m.group(1).replace(",","")),m))
      except:pass
    if vals:
      v,m=max(vals,key=lambda x:x[0]);out["area_sqm"]=_field(round(v,1),m,.85)
    # Long leasehold/headlease residue, ground rent and service charge.
    m=re.search(r"(?:long leasehold|leasehold)[^.;]{0,180}(?:years? remaining|unexpired term|term of)[^.;]{0,100}",t,re.I)
    if m:out["tenure_detail"]=_field(m.group(0).strip(),m,.82)
    m=re.search(r"ground rent[^£]{0,60}£\s*([\d,]+(?:\.\d+)?)",t,re.I)
    if m:out["ground_rent"]=_field(_money(m.group(1)),m,.9)
    m=re.search(r"service charge[^£]{0,80}£\s*([\d,]+(?:\.\d+)?)",t,re.I)
    if m:out["service_charge"]=_field(_money(m.group(1)),m,.9)
    # VAT / TOGC.
    if re.search(r"VAT\s+not\s+applicable|no\s+VAT",t,re.I):
      m=re.search(r"VAT\s+not\s+applicable|no\s+VAT",t,re.I);out["vat"]=_field("NOT APPLICABLE",m,.95)
    elif re.search(r"TOGC|transfer of a going concern",t,re.I):
      m=re.search(r"TOGC|transfer of a going concern",t,re.I);out["vat"]=_field("TOGC indicated",m,.9)
    elif re.search(r"(?:plus|subject to)\s+VAT|VAT\s+is\s+payable",t,re.I):
      m=re.search(r"(?:plus|subject to)\s+VAT|VAT\s+is\s+payable",t,re.I);out["vat"]=_field("VAT applicable",m,.9)
    return {k:asdict(v) for k,v in out.items()}

def merge_enrichment(lot:dict, extracted:dict)->dict:
    """Fill missing lot fields without overwriting stronger existing facts."""
    out=dict(lot)
    for key,item in (extracted or {}).items():
      value=item.get("value") if isinstance(item,dict) else item
      if value in (None,""):continue
      if not out.get(key):out[key]=value
    out["particulars_evidence"]={k:{"source_text":v.get("source_text","") ,"confidence":v.get("confidence")} for k,v in (extracted or {}).items()}
    return out
