"""End-to-end service layer for Auction Sniper Buyer Due Diligence."""
from __future__ import annotations
from dataclasses import dataclass,asdict
from typing import Any,Iterable
import time
from legal_pack_ingest import ingest_pack
from legal_pack_engine import analyse_pack
from legal_pack_report import build_report,render_text
REPORT_PRICE_GBP=25.00;VAT_RATE=0.20
@dataclass
class AnalysisCost:
 input_files:int=0;expanded_files:int=0;accepted_documents:int=0;visual_review_items:int=0;conversion_required_items:int=0;unsupported_items:int=0;duplicate_files:int=0;total_bytes:int=0;total_pages:int=0;extracted_chars:int=0;elapsed_seconds:float=0.0;ai_cost_gbp:float=0.0;infrastructure_cost_gbp:float=0.0;sale_price_ex_vat_gbp:float=REPORT_PRICE_GBP;vat_gbp:float=REPORT_PRICE_GBP*VAT_RATE;sale_price_inc_vat_gbp:float=REPORT_PRICE_GBP*(1+VAT_RATE);estimated_gross_margin_gbp:float=REPORT_PRICE_GBP

def analyse_uploaded_pack(property_ref:str,files:Iterable[tuple[str,bytes]],catalogue:dict[str,Any]|None=None)->dict[str,Any]:
 started=time.perf_counter();file_list=list(files);ingested=ingest_pack(file_list);due=analyse_pack(property_ref,ingested.documents,catalogue or {});model=build_report(due,catalogue or {})
 counts={s:sum(1 for a in ingested.assets if a.status==s) for s in ("analysed","partial","visual_review_required","conversion_required","unsupported","expanded")}
 cost=AnalysisCost(input_files=len(file_list),expanded_files=ingested.expanded_files,accepted_documents=len(ingested.documents),visual_review_items=counts["visual_review_required"],conversion_required_items=counts["conversion_required"],unsupported_items=counts["unsupported"],duplicate_files=len(ingested.duplicates),total_bytes=ingested.total_bytes,total_pages=ingested.total_pages,extracted_chars=sum(len(d.text) for d in ingested.documents),elapsed_seconds=round(time.perf_counter()-started,4))
 cost.estimated_gross_margin_gbp=round(cost.sale_price_ex_vat_gbp-cost.ai_cost_gbp-cost.infrastructure_cost_gbp,2)
 coverage={"uploaded_files":len(file_list),"expanded_items":ingested.expanded_files,"machine_read_documents":len(ingested.documents),"analysed":counts["analysed"],"partial":counts["partial"],"visual_review_required":counts["visual_review_required"],"conversion_required":counts["conversion_required"],"unsupported":counts["unsupported"],"duplicates":len(ingested.duplicates)}
 incomplete=bool(ingested.issues or due.missing or due.conflicts or counts["visual_review_required"] or counts["conversion_required"] or counts["unsupported"] or counts["partial"])
 return {"property":property_ref,"report":model,"report_text":render_text(model),"analysis":due.to_dict(),"ingestion":{"coverage":coverage,"documents":[{"name":d.name,"type":d.doc_type.value,"sha256":d.sha256,"metadata":d.metadata} for d in ingested.documents],"assets":[asdict(a) for a in ingested.assets],"issues":[asdict(i) for i in ingested.issues],"duplicates":ingested.duplicates},"commercial":{"price_ex_vat_gbp":REPORT_PRICE_GBP,"vat_rate":VAT_RATE,"price_inc_vat_gbp":round(REPORT_PRICE_GBP*(1+VAT_RATE),2)},"cost_ledger":asdict(cost),"status":"completed_with_warnings" if incomplete else "completed"}
