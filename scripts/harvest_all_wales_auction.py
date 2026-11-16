"""Collect the surviving first-party All Wales Auction catalogue PDFs.

Each retained catalogue is an event snapshot. Download each source once, hash and
preserve it, then extract only the explicitly identified All Wales lot range.
Unavailable sources are checkpointed and do not prevent accessible catalogues from
being banked. Unknown outcomes/prices remain null.
"""
from __future__ import annotations
import argparse, base64, gzip, io, json, re, sys
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pypdf import PdfReader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

HEADERS={"User-Agent":"Commercial-Auction-Sniper/1.0 (+historical lot research)"}
CATALOGUES=[
 {"date":"2020-12-15","url":"https://www.allwalesauction.com/downloads/301120-december-2020-full-catalogue.pdf","lots":(118,126),"label":"2020-12-15"},
 {"date":"2021-03-09","url":"https://www.allwalesauction.com/downloads/220221-march-catalogue.pdf","lots":(131,136),"label":"2021-03-09"},
 {"date":"2021-05-18","url":"https://www.allwalesauction.com/downloads/full-catalogue-may-2021.pdf","lots":(115,120),"label":"2021-05-18"},
 {"date":"2021-07-27","url":"https://www.allwalesauction.com/downloads/120721-july-catalogue.pdf","lots":(157,162),"label":"2021-07-27"},
]
PC=corpus.PC
LOT=re.compile(r"(?im)^\s*lot\s+(\d+[A-Z]?)\b")
GUIDE=re.compile(r"(?i)(?:guide|asking)\s*(?:price)?\s*[:£-]?\s*£?\s*([\d,]+(?:\.\d+)?)")
ACHIEVED=re.compile(r"(?i)\b(?:sold\s+(?:for|at)|selling\s+price|price\s+achieved|achieved)\s*[:£-]?\s*£?\s*([\d,]+(?:\.\d+)?)")
EXPLICIT_STATUS=re.compile(r"(?im)^\s*(sold prior|sold|withdrawn|unsold|no bid|not sold|postponed)\s*$")

def clean(s):
    return re.sub(r"\s+"," ",s or "").strip(" ,\xa0")

def money(m):
    try: return int(round(float(m.group(1).replace(",",""))))
    except Exception: return None

def extract_pdf(raw):
    reader=PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)

def parse_lots(text,cfg,evidence):
    matches=list(LOT.finditer(text)); rows=[]
    lo,hi=cfg["lots"]
    for i,m in enumerate(matches):
        token=m.group(1)
        n=int(re.match(r"\d+",token).group())
        if not (lo<=n<=hi): continue
        block=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        block=clean(block)
        pcs=list(PC.finditer(block))
        address=None; postcode=None
        if pcs:
            pm=pcs[0]; postcode=pm.group().upper()
            before=block[max(0,pm.start()-240):pm.start()]
            lines=[clean(x) for x in re.split(r"[.;]\s+|\n",before) if clean(x)]
            address=clean((lines[-1] if lines else "")+" "+postcode) or None
        gm=GUIDE.search(block)
        am=ACHIEVED.search(block)
        sm=EXPLICIT_STATUS.search(block)
        guide=money(gm) if gm else None
        sale=money(am) if am else None
        status=clean(sm.group(1)).casefold().replace(" ","_") if sm else None
        source_id=f"all-wales-auction:{cfg['label']}:lot:{token}"
        row=corpus.base_row("All Wales Auction",source_id,cfg["date"],token,source_id,cfg["url"])
        row.update({
          "appearance_id":f"All Wales Auction|{cfg['date']}|lot:{token}",
          "address":address,"postcode":postcode,"locality":None,
          "sector":corpus.sector(block),"property_type":None,
          "guide_price":guide,"sale_price":sale,"status":status,
          "description":block[:2500],"image_urls":[],"property_id":None,
          "identity_method":"first_party_catalogue_event_date_and_published_lot_number",
          "record_quality":"address_record" if address else "partial",
          "source_position":n,"source_property_id":source_id,
          "source_price_label":"guide" if guide is not None else None,
          "source_price_text":clean(gm.group(0)) if gm else None,
          "source_result_flag":clean(sm.group(1)) if sm else None,
          "auction_date_basis":"published catalogue auction event date",
          "source_evidence":evidence,
        })
        rows.append(row)
    ids=[r["appearance_id"] for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate All Wales lot identities")
    return rows

def harvest():
    session=requests.Session()
    retry=Retry(total=3, connect=3, read=3, status=3, backoff_factor=1.0, status_forcelist=(429,500,502,503,504), allowed_methods=frozenset({"GET"}), raise_on_status=False)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    observed=[]; summaries=[]
    out=corpus.DATA/"appearances/all_wales_auction/canonical.jsonl.gz"
    existing=list(corpus.iter_rows(out)) if out.exists() else []
    before={r["appearance_id"] for r in existing}
    for cfg in CATALOGUES:
        try:
            r=session.get(cfg["url"],headers=HEADERS,timeout=90)
            if r.status_code == 404:
                summaries.append({"date":cfg["date"],"source_url":cfg["url"],"expected_lots":cfg["lots"][1]-cfg["lots"][0]+1,
                                  "captured_lots":0,"complete":False,"source_failure":"HTTP 404"})
                continue
            r.raise_for_status()
        except requests.RequestException as exc:
            summaries.append({"date":cfg["date"],"source_url":cfg["url"],"expected_lots":cfg["lots"][1]-cfg["lots"][0]+1,
                              "captured_lots":0,"complete":False,"source_failure":f"{type(exc).__name__}: {exc}"})
            continue
        raw=r.content
        if len(raw)<10000:
            summaries.append({"date":cfg["date"],"source_url":cfg["url"],"expected_lots":cfg["lots"][1]-cfg["lots"][0]+1,
                              "captured_lots":0,"complete":False,"source_failure":"unexpectedly short PDF"})
            continue
        sha=corpus.digest(raw)
        snap=corpus.DATA/"sources/all-wales-auction"/f"{cfg['label']}-{sha[:16]}.json.gz"
        evidence={"source_url":r.url,"retrieved_at":corpus.now(),"sha256":sha,
          "snapshot_path":str(snap.relative_to(corpus.ROOT)),
          "basis":"first-party dated All Wales Auction catalogue PDF",
          "published_lot_range":list(cfg["lots"])}
        corpus.save_gzip(snap,{"evidence":evidence,"pdf_base64":base64.b64encode(raw).decode("ascii")})
        text=extract_pdf(raw)
        rows=parse_lots(text,cfg,evidence)
        expected=cfg["lots"][1]-cfg["lots"][0]+1
        summaries.append({"date":cfg["date"],"source_url":cfg["url"],"expected_lots":expected,
          "captured_lots":len(rows),"complete":len(rows)==expected,"sha256":sha})
        observed.extend(rows)
    merged={r["appearance_id"]:r for r in existing}
    for r in observed:
        if r["appearance_id"] in merged and merged[r["appearance_id"]] != r:
            continue
        merged[r["appearance_id"]]=r
    corpus.write_rows("all_wales_auction/canonical",list(merged.values()))
    added=[r for k,r in merged.items() if k not in before]
    summary={"checked_at":corpus.now(),"catalogues":summaries,
      "appearances_captured":len(observed),"run_new_appearances":len(added),
      "run_new_address_records":sum(bool(r.get("address")) for r in added),
      "run_new_partial_lots":sum(1 for r in added if not r.get("address")),
      "run_new_guides":sum(r.get("guide_price") is not None for r in added),
      "run_new_sale_prices":sum(r.get("sale_price") is not None for r in added),
      "commercial_mixed_use":sum((r.get("sector") or "").casefold() in {"commercial","mixed-use"} for r in added),
      "source_failures":[s for s in summaries if s.get("source_failure")]}
    corpus.save_json(corpus.DATA/"all_wales_auction_collection.json",summary)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__":
    argparse.ArgumentParser().parse_args()
    harvest()
