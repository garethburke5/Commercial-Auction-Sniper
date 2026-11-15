"""Collect the surviving first-party All Wales Auction PDF catalogues.

The retained catalogues are dated event snapshots. Each PDF is downloaded once,
hashed, preserved as a compressed base64 snapshot, then split conservatively by
published lot number. Unknown address/price/outcome fields remain null rather
than being inferred from narrative text.
"""
from __future__ import annotations
import argparse, base64, gzip, io, json, re, sys
from datetime import date
from pathlib import Path
import requests
from pypdf import PdfReader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_corpus as corpus

HEADERS={"User-Agent":"Commercial-Auction-Sniper/1.0 (+historical lot research)"}
CATALOGUES=[
 {"date":"2020-11-30","url":"https://www.allwalesauction.com/downloads/301120-december-2020-full-catalogue.pdf","lots":(118,126),"label":"2020-11-30"},
 {"date":"2021-03-01","url":"https://www.allwalesauction.com/downloads/220221-march-catalogue.pdf","lots":(131,136),"label":"2021-03"},
 {"date":"2021-05-01","url":"https://www.allwalesauction.com/downloads/full-catalogue-may-2021.pdf","lots":(115,120),"label":"2021-05"},
 {"date":"2021-07-12","url":"https://www.allwalesauction.com/downloads/120721-july-catalogue.pdf","lots":(157,162),"label":"2021-07"},
]
PC=corpus.PC
MONEY=re.compile(r"£\s*([\d,]+(?:\.\d+)?)",re.I)
LOT=re.compile(r"(?im)^\s*lot\s+(\d+)\b")
GUIDE=re.compile(r"(?i)(?:guide|asking)\s*(?:price)?\s*[:£-]?\s*£?\s*([\d,]+(?:\.\d+)?)")
SOLD=re.compile(r"(?i)(?:sold|sold prior|selling price|achieved|price achieved)\s*[:£-]?\s*£?\s*([\d,]+(?:\.\d+)?)")
STATUS=re.compile(r"(?i)\b(sold prior|sold|withdrawn|unsold|not sold|no bid|available)\b")

def clean(s): return re.sub(r"\s+"," ",s or "").strip(" ,\xa0")

def money(m):
    try: return int(round(float(m.group(1).replace(",","")))
    except Exception: return None

def extract_pdf(raw):
    reader=PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)

def parse_lots(text,cfg,evidence):
    matches=list(LOT.finditer(text)); rows=[]
    lo,hi=cfg["lots"]
    for i,m in enumerate(matches):
        n=int(m.group(1))
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
        gm=GUIDE.search(block); sm=SOLD.search(block); st=STATUS.search(block)
        guide=money(gm) if gm else None
        sale=money(sm) if sm else None
        status=clean(st.group(1)).casefold().replace(" ","_") if st else "unknown"
        if status=="sold" and sale is None:
            # A bare sold marker is evidence of outcome, not a price.
            sale=None
        source_id=f"all-wales-auction:{cfg['label']}:lot:{n}"
        row=corpus.base_row("All Wales Auction",source_id,cfg["date"],str(n),source_id,cfg["url"])
        row.update({
          "appearance_id":f"All Wales Auction|{cfg['date']}|lot:{n}",
          "address":address,"postcode":postcode,"locality":None,
          "sector":corpus.sector(block),"property_type":None,
          "guide_price":guide,"sale_price":sale,"status":status,
          "description":block[:2500],"image_urls":[],"property_id":None,
          "identity_method":"first_party_catalogue_date_and_published_lot_number",
          "record_quality":"address_record" if address else "partial",
          "source_position":n,"source_property_id":source_id,
          "source_price_label":None,"source_price_text":None,
          "source_result_flag":clean(st.group(1)) if st else None,
          "auction_date_basis":"published catalogue event date",
          "source_evidence":evidence,
        })
        rows.append(row)
    ids=[r["appearance_id"] for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate All Wales lot identities")
    return rows

def harvest():
    observed=[]; summaries=[]
    out=corpus.DATA/"appearances/all_wales_auction/canonical.jsonl.gz"
    existing=list(corpus.iter_rows(out)) if out.exists() else []
    before={r["appearance_id"] for r in existing}
    for cfg in CATALOGUES:
        r=requests.get(cfg["url"],headers=HEADERS,timeout=90); r.raise_for_status()
        raw=r.content
        if len(raw)<10000: raise ValueError("unexpectedly short PDF: "+cfg["url"])
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
            # Never overwrite a previously banked row with a parser variant.
            continue
        merged[r["appearance_id"]]=r
    corpus.write_rows("all_wales_auction/canonical",list(merged.values()))
    added=[r for k,r in merged.items() if k not in before]
    summary={"checked_at":corpus.now(),"catalogues":summaries,
      "appearances_captured":len(observed),"run_new_appearances":len(added),
      "run_new_address_records":sum(bool(r.get("address")) for r in added),
      "run_new_partial_lots":sum(not r.get("address")) for r in added,
      "run_new_guides":sum(r.get("guide_price") is not None for r in added),
      "run_new_sale_prices":sum(r.get("sale_price") is not None for r in added),
      "commercial_mixed_use":sum((r.get("sector") or "").casefold() in {"commercial","mixed-use"} for r in added)}
    corpus.save_json(corpus.DATA/"all_wales_auction_collection.json",summary)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__":
    argparse.ArgumentParser().parse_args()
    harvest()
