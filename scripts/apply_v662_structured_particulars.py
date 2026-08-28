from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.[^"]+"','BUILD = "V6.62-STRUCTURED-PARTICULARS"',s,count=1)

anchor='''def _deep_page_evidence(url):'''
helper=r'''
def _structured_particulars(text):
    """Extract high-value commercial particulars with semantic labels, not loose money matching."""
    text=norm(text or '')
    out={}

    # Tenant / occupier
    tenant_patterns=[
        r"(?:entirely|fully)?\s*let\s+to\s+([^.;]{2,120}?)(?=\s+on\s+a\s+lease|\s+on\s+lease|\s+for\s+a\s+term|\s+at\s+£|[.;])",
        r"tenant\s*[:\-]\s*([^.;]{2,120})",
    ]
    for pat in tenant_patterns:
        m=re.search(pat,text,re.I)
        if m:
            out['tenant']=norm(m.group(1)).strip(' -,:')[:120]
            break

    # Lease term and commencement. Handles '5 years from August 2027'.
    m=re.search(r"lease\s+for\s+a\s+term\s+of\s+(\d+(?:\.\d+)?)\s+years?\s+from\s+([A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4})",text,re.I)
    if m:
        out['lease_term_years']=float(m.group(1))
        out['lease_start']=norm(m.group(2))
    m=re.search(r"lease\s+(?:expir(?:y|ing|es)|to expire)\s*(?:on|in)?\s*([A-Za-z]+\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4})",text,re.I)
    if m: out['lease_expiry']=norm(m.group(1))
    if 'lease_expiry' not in out:
        m=re.search(r"lease\s+expiring\s+(\d{4})",text,re.I)
        if m: out['lease_expiry']=m.group(1)

    # Current passing rent - deliberately requires current/tenancy wording.
    current_patterns=[
        r"(?:investment\s+)?let\s+at\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
        r"rent\s*[:\-]?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
        r"at\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\s*(?:exclusive|$)",
    ]
    for pat in current_patterns:
        m=re.search(pat,text,re.I)
        if m:
            try: out['passing_rent']=float(m.group(1).replace(',',''))
            except: pass
            break

    # Accommodation. Capture totals first; otherwise sum clearly labelled floors.
    totals=[]
    for m in re.finditer(r"Total\s*[-:]?\s*([\d,.]+)\s*sq\s*m\s*\(([\d,]+)\s*sq\s*ft\)",text,re.I):
        try: totals.append((float(m.group(2).replace(',','')),float(m.group(1).replace(',',''))))
        except: pass
    if totals:
        out['area_sqft'],out['area_sqm']=max(totals,key=lambda x:x[0])
    else:
        floors=[]
        for m in re.finditer(r"(?:Ground|First|Second|Basement|Lower Ground|Upper)\s+Floor[^.;]{0,80}?([\d,.]+)\s*sq\s*m\s*\(([\d,]+)\s*sq\s*ft\)",text,re.I):
            try: floors.append((float(m.group(2).replace(',','')),float(m.group(1).replace(',',''))))
            except: pass
        if floors:
            out['area_sqft']=sum(x[0] for x in floors); out['area_sqm']=sum(x[1] for x in floors)

    # VAT
    if re.search(r"VAT\s+is\s+not\s+applicable|VAT\s+not\s+applicable|not\s+subject\s+to\s+VAT",text,re.I): out['vat']='Not applicable / VAT-free'
    elif re.search(r"VAT\s+(?:is\s+)?applicable|plus\s+VAT|subject\s+to\s+VAT",text,re.I): out['vat']='Applicable'

    # EPC rating if actually shown.
    m=re.search(r"(?:EPC|Energy Performance Certificate|Energy Performance)\s*(?:rating|asset rating)?\s*[:\-]?\s*([A-G])(?:\s*\(?([0-9]{1,3})\)?)?\b",text,re.I)
    if m: out['epc_rating']=m.group(1).upper()+(f" ({m.group(2)})" if m.group(2) else '')
    return out


def _apply_structured_particulars(row,text):
    r=dict(row); sp=_structured_particulars(text)
    if sp.get('tenant'): r['tenant']=sp['tenant']
    if sp.get('passing_rent') is not None:
        r['rent']=sp['passing_rent']; r['rent_status']='CURRENT / PASSING'
    if sp.get('lease_term_years') is not None: r['lease_term_years']=sp['lease_term_years']
    if sp.get('lease_start'): r['lease_start']=sp['lease_start']
    if sp.get('lease_expiry'): r['lease_expiry']=sp['lease_expiry']
    if sp.get('area_sqft'): r['area_sqft']=sp['area_sqft']
    if sp.get('area_sqm'): r['area_sqm']=sp['area_sqm']
    if sp.get('vat'): r['vat']=sp['vat']
    if sp.get('epc_rating'): r['epc_rating']=sp['epc_rating']
    if r.get('guide') and r.get('rent'): r['yield']=100*float(r['rent'])/float(r['guide'])
    return r

'''
if anchor not in s: raise SystemExit('deep page evidence anchor missing')
s=s.replace(anchor,helper+anchor,1)

# Apply structured extraction to deep page + legal text before loose semantic normalisation.
old='''        if ev.get('legal_links'):\n            r['legal_links']=ev['legal_links']; r['legal_pack_url']=ev['legal_links'][0]\n        return i,_normalise_rent_semantics(r)'''
new='''        if ev.get('legal_links'):\n            r['legal_links']=ev['legal_links']; r['legal_pack_url']=ev['legal_links'][0]\n        combined=norm((ev.get('page_text') or '')+' '+(ev.get('legal_text') or ''))\n        r=_apply_structured_particulars(r,combined)\n        return i,_normalise_rent_semantics(r)'''
if old not in s: raise SystemExit('deep enrichment apply anchor missing')
s=s.replace(old,new,1)

# Feed structured fields into investment facts before regex fallbacks.
needle='''    tenant=None\n    for pat in ['''
replace='''    tenant=p.get("tenant") or None\n    for pat in ['''
if needle not in s: raise SystemExit('tenant anchor missing')
s=s.replace(needle,replace,1)
# Prevent fallback from overwriting structured tenant.
s=s.replace('''        if m:\n            tenant=norm(m.group(1)).strip("'\\\"“”")[:90]\n            if tenant: break''','''        if m and not tenant:\n            tenant=norm(m.group(1)).strip("'\\\"“”")[:90]\n            if tenant: break''',1)

# Structured lease facts and future-start warning.
needle='''    if tenant: f["Tenant"]=tenant\n    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'\n'''
replace='''    if tenant: f["Tenant"]=tenant\n    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'\n    if p.get("lease_term_years") is not None: f["Lease term"]=f'{p["lease_term_years"]:g} years'\n    if p.get("lease_start"): f["Lease commencement"]=str(p["lease_start"])\n    if p.get("lease_expiry"): f["Lease expiry"]=str(p["lease_expiry"])\n    if p.get("area_sqft"): f["Floor area"]=f'{float(p["area_sqft"]):,.0f} sq ft / {float(p.get("area_sqm") or float(p["area_sqft"])/10.7639):,.1f} sq m'\n    if p.get("lease_start") and re.search(r"\\b2027\\b",str(p.get("lease_start"))) and "2026" in time.strftime("%Y"):\n        f["Lease timing note"]="Lease commencement stated as 2027 — future-dated from the current auction date; verify legal pack / agreement for lease."\n        chips.append("FUTURE LEASE START")\n'''
if needle not in s: raise SystemExit('structured fact anchor missing')
s=s.replace(needle,replace,1)

# Avoid replacing structured floor area later.
s=s.replace('''    if rel.get("sqft"):\n        f["Floor area"]=f'{rel["sqft"]:,.0f} sq ft / {rel["sqm"]:,.0f} sq m' ''','''    if rel.get("sqft") and "Floor area" not in f:\n        f["Floor area"]=f'{rel["sqft"]:,.0f} sq ft / {rel["sqm"]:,.0f} sq m' ''',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.62 structured particulars extraction applied')
