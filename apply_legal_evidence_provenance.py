from pathlib import Path

p=Path('legal_pack_engine.py')
s=p.read_text(encoding='utf-8')
old='''@dataclass\nclass Evidence: document:str; document_type:str; excerpt:str=""; page:int|None=None; clause:str|None=None; confidence:float=1.0'''
new='''@dataclass\nclass Evidence:\n document:str; document_type:str; excerpt:str=""; page:int|None=None; clause:str|None=None; confidence:float=1.0\n paragraph:int|None=None; table:int|None=None; row:int|None=None; sheet:str|None=None\n scope:str="unknown"; temporal_status:str="unspecified"; authority:str="document"'''
if old not in s: raise SystemExit('Evidence dataclass anchor missing')
s=s.replace(old,new,1)
old2='''def _ev(d,x,clause=None,confidence=1.0): return Evidence(d.name,d.doc_type.value,x[:700],clause=clause,confidence=confidence)'''
new2='''def _locate(metadata,needle):\n if not needle:return {}\n target=re.sub(r"\\s+"," ",needle).strip().lower()\n def hit(text):return target in re.sub(r"\\s+"," ",text or "").lower()\n for p in metadata.get("pages",[]):\n  if hit(p.get("text","")):return {"page":p.get("page")}\n for p in metadata.get("paragraphs",[]):\n  if hit(p.get("text","")):return {"paragraph":p.get("paragraph")}\n for t in metadata.get("tables",[]):\n  for row in t.get("rows",[]):\n   if hit(" | ".join(row.get("cells",[]))):return {"table":t.get("table"),"row":row.get("row")}\n for sh in metadata.get("sheets",[]):\n  for row in sh.get("rows",[]):\n   if hit(" | ".join(row.get("cells",[]))):return {"sheet":sh.get("sheet"),"row":row.get("row")}\n return {}\n\ndef _ev(d,x,clause=None,confidence=1.0,scope="unknown",temporal_status="unspecified",authority="document"):\n loc=_locate(d.metadata or {},x)\n return Evidence(d.name,d.doc_type.value,x[:700],page=loc.get("page"),clause=clause,confidence=confidence,paragraph=loc.get("paragraph"),table=loc.get("table"),row=loc.get("row"),sheet=loc.get("sheet"),scope=scope,temporal_status=temporal_status,authority=authority)'''
if old2 not in s: raise SystemExit('_ev anchor missing')
s=s.replace(old2,new2,1)
# Mark the most important forward/historical evidence semantically without rewriting extraction logic.
s=s.replace('_ev(d,"tenancy expired on 30 April 2024")','_ev(d,"tenancy expired on 30 April 2024",temporal_status="historical",authority="special_conditions")')
s=s.replace('_ev(d,"remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954")','_ev(d,"remains in occupation pursuant to Part II of the Landlord and Tenant Act 1954",temporal_status="current",authority="special_conditions")')
s=s.replace('[_ev(d,m.group(0))]));_put(r,Finding("proposed_term"','[_ev(d,m.group(0),temporal_status="proposed",authority="special_conditions")]));_put(r,Finding("proposed_term"',1)
s=s.replace('[_ev(d,m.group(0))]))\n  if "renewal tenancy has not yet been completed"','[_ev(d,m.group(0),temporal_status="proposed",authority="special_conditions")]))\n  if "renewal tenancy has not yet been completed"',1)
s=s.replace('_ev(d,"renewal tenancy has not yet been completed")','_ev(d,"renewal tenancy has not yet been completed",temporal_status="current",authority="special_conditions")')
s=s.replace('_ev(d,"Boots Opticians Professional Services")','_ev(d,"Boots Opticians Professional Services",scope="tenant_demise",temporal_status="historical",authority="lease")')
s=s.replace('_ev(d,m.group(0))]))\n elif d.doc_type==DocType.COURT','_ev(d,m.group(0),scope="subject_property",temporal_status="current",authority="epc_certificate")]))\n elif d.doc_type==DocType.COURT',1)
s=s.replace('"schema":"1.1"','"schema":"1.2"')
p.write_text(s,encoding='utf-8')
