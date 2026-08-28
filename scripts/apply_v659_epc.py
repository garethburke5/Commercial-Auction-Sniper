from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
# Build marker
s=re.sub(r'BUILD = "V6\.[^"]+"','BUILD = "V6.59-EPC-CAPTURE"',s,count=1)
# Add EPC to source text inputs if already captured in row
old='''        p.get("tenure"),
        p.get("vat"),
    ]'''
new='''        p.get("tenure"),
        p.get("vat"),
        p.get("epc"),
        p.get("epc_rating"),
    ]'''
if old in s: s=s.replace(old,new,1)
# EPC parsing in investment facts, before occupation
anchor='''    if re.search(r"\\bTOGC\\b|transfer of a business as a going concern",text,re.I): f["TOGC"]="Mentioned"; chips.append("TOGC")

    if re.search(r"vacant possession|\\bvacant\\b",text,re.I):'''
insert='''    if re.search(r"\\bTOGC\\b|transfer of a business as a going concern",text,re.I): f["TOGC"]="Mentioned"; chips.append("TOGC")

    # EPC: show only where the captured auction particulars give positive evidence.
    # Accept standard letter ratings, numeric asset ratings and explicit EPC references.
    epc=None
    for pat in [
        r"(?:EPC|Energy Performance Certificate|Energy Performance)\\s*(?:rating|asset rating|grade)?\\s*[:\\-]?\\s*([A-G])(?:\\s*\\(?([0-9]{1,3})\\)?)?\\b",
        r"(?:EPC|Energy Performance Certificate|Energy Performance)\\s*(?:rating|asset rating)?\\s*[:\\-]?\\s*([0-9]{1,3})\\s*\\(?([A-G])\\)?\\b",
        r"\\bEPC\\s+([A-G])\\b",
    ]:
        m=re.search(pat,text,re.I)
        if m:
            vals=[g for g in m.groups() if g]
            letter=next((v.upper() for v in vals if re.fullmatch(r"[A-G]",v,re.I)),None)
            number=next((v for v in vals if v.isdigit()),None)
            epc=(letter + (f" ({number})" if number else "")) if letter else (f"Asset rating {number}" if number else None)
            if epc: break
    if not epc:
        raw_epc=p.get("epc_rating") or p.get("epc")
        if raw_epc and str(raw_epc).strip().lower() not in ("unknown","n/a","none","-"):
            epc=norm(str(raw_epc))[:80]
    if epc:
        f["EPC"]=epc
        chips.append("EPC "+epc)
    elif re.search(r"energy performance certificate|\\bEPC\\b",text,re.I):
        # Useful evidence exists but do not invent a rating.
        f["EPC"]="Referenced — rating not captured"
        chips.append("EPC REFERENCED")

    if re.search(r"vacant possession|\\bvacant\\b",text,re.I):'''
if anchor not in s: raise SystemExit('EPC anchor not found')
s=s.replace(anchor,insert,1)
# Make EPC visible on card meta line as well as details/chip when available
oldmeta='''        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)'''
newmeta='''        _epc_raw=x.get("epc_rating") or x.get("epc")
        _epc_meta=("EPC "+str(_epc_raw)) if _epc_raw and str(_epc_raw).strip().lower() not in ("unknown","n/a","none","-") else None
        meta=" · ".join(v for v in [x.get("date"),x.get("tenure"),_epc_meta,("VAT "+x["vat"]) if x.get("vat") and x["vat"]!="UNKNOWN" else None] if v)'''
if oldmeta in s: s=s.replace(oldmeta,newmeta,1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.59 EPC capture/display applied')
