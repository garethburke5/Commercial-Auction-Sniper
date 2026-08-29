from pathlib import Path

MODULE = r'''"""Source-agnostic exact-page enrichment for Auction Sniper.

Every auctioneer collector should discover exact property URLs, then pass the
exact page through this module. The output schema is deliberately shared across
sources so cards can render consistent investment facts without site-specific UI
logic. Source-specific collectors may still supply stronger values/images; this
module fills or corrects fields only when the exact page contains evidence.
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup

POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)

BOILERPLATE = (
    "for sale by auction", "auction date", "future auction dates", "view lot",
    "view details", "register to bid", "legal pack", "request a viewing",
    "live stream", "contact us", "property search", "previous lot", "next lot",
)
RELATED_MARKERS = (
    "you may also be interested in", "similar properties", "other properties",
    "other lots", "related properties", "recommended properties",
)


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def money(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _first(patterns, text, flags=re.I):
    for p in patterns:
        m = re.search(p, text, flags)
        if m:
            return clean_text(m.group(1))
    return None


def _amount(patterns, text):
    return money(_first(patterns, text))


def clean_address(raw):
    s = clean_text(raw)
    pm = POSTCODE.search(s)
    if pm:
        s = s[:pm.end()]
    for phrase in BOILERPLATE:
        i = s.lower().find(phrase)
        if i == 0:
            s = clean_text(s[len(phrase):].lstrip(" |-–—:"))
    return s


def extract_address(soup):
    h = soup.find("h1")
    if h:
        v = clean_address(h.get_text(" ", strip=True))
        if len(v) >= 5:
            return v
    for attrs in ({"property": "og:title"}, {"name": "twitter:title"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            v = clean_address(tag["content"])
            if POSTCODE.search(v):
                return v
    return None


def _scoped_text(soup):
    main = soup.find("main") or soup
    text = clean_text(main.get_text(" ", strip=True))
    low = text.lower()
    cuts = [low.find(marker) for marker in RELATED_MARKERS if low.find(marker) >= 0]
    if cuts:
        text = text[:min(cuts)]
    return clean_text(text)


def _rent_text_without_historical_clauses(text):
    patterns = (
        r"\bpreviously\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bformerly\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bhistorically\s+(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bwas\s+(?:previously\s+)?(?:let|leased)[^.]{0,180}(?:\.|$)",
        r"\bformer\s+rent[^.]{0,150}(?:\.|$)",
        r"\bprevious\s+rent[^.]{0,150}(?:\.|$)",
    )
    cleaned = text
    for pattern in patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.I)
    return clean_text(cleaned)


def _extract_epc(text):
    bands = []
    patterns = (
        r"\bEPC\s+Band\s+([A-G])\b",
        r"\bEPC(?:\s+Rating)?\s*(?:\||:|-)?\s*([A-G](?:\s*\(\s*\d{1,3}\s*\))?)",
        r"Energy Performance Certificate[^A-G]{0,30}([A-G](?:\s*\(\s*\d{1,3}\s*\))?)",
    )
    for p in patterns:
        for m in re.finditer(p, text, re.I):
            value = clean_text(m.group(1)).upper().replace("  ", " ")
            if value not in bands:
                bands.append(value)
    return " / ".join(bands) if bands else None


def _extract_area(text):
    pair_patterns = (
        r"(?:total\s+floor\s+area(?:\s+of)?\s+)?(?:approximately|approx\.?|circa)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s*\)?",
        r"(?:total\s+floor\s+area|total\s+area|accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)[^\d]{0,20}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    for p in pair_patterns:
        m = re.search(p, text, re.I)
        if m:
            sqm = money(m.group(1)); sqft = money(m.group(2))
            if sqm and sqft:
                return sqft, sqm
    total_sqft = _amount([
        r"(?:Total(?:\s+Floor)?\s+Area|Total\s+Accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
        r"(?:approximately|approx\.?|circa)\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    ], text)
    total_sqm = _amount([
        r"(?:Total(?:\s+Floor)?\s+Area|Total\s+Accommodation)[^\d]{0,35}([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
        r"(?:approximately|approx\.?|circa)\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
    ], text)
    if total_sqft and not total_sqm:
        total_sqm = total_sqft / 10.7639
    elif total_sqm and not total_sqft:
        total_sqft = total_sqm * 10.7639
    return total_sqft, total_sqm


def extract_particulars(html, source="", url=""):
    soup = BeautifulSoup(html, "lxml")
    text = _scoped_text(soup)
    rent_text = _rent_text_without_historical_clauses(text)
    out = {"address": extract_address(soup)}

    guide_status = None
    if re.search(r"Guide\*?\s*(?:\||:|-)?\s*Refer\s+to\s+Auctioneer", text, re.I):
        guide = None
        guide_status = "Refer to Auctioneer"
    else:
        guide = _amount([
            r"Guide(?:\s+Price)?\*?\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
            r"Guide\s+Price\s+of\s+£\s*([\d,]+(?:\.\d+)?)",
            r"Starting\s+Bid\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
            r"Available\s+at\s*£\s*([\d,]+(?:\.\d+)?)",
        ], text)
    out["guide"] = guide
    if guide_status:
        out["guide_status"] = guide_status

    out["rent"] = _amount([
        r"(?:currently\s+)?(?:let|leased)\s+(?:at|for)\s+£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
        r"(?:current|passing)\s+(?:rent|rental|income)[^£]{0,45}£\s*([\d,]+(?:\.\d+)?)",
        r"(?:producing|rental income(?:\s+of)?|annual income(?:\s+of)?)[^£]{0,35}£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)?",
        r"\bRent\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:p\.?a\.?|per annum|pa)",
    ], rent_text)
    out["erv"] = _amount([
        r"(?:ERV|estimated rental value|market rent)[^£]{0,40}£\s*([\d,]+(?:\.\d+)?)",
    ], text)

    labelled_tenure = _first([
        r"\bTenure\s*(?:\||:|-)?\s*(Freehold|Long\s+Leasehold|Leasehold)\b",
    ], text)
    out["tenure"] = (clean_text(labelled_tenure).title() if labelled_tenure else
                     "Freehold" if re.search(r"\bfreehold\b", text, re.I)
                     else "Leasehold" if re.search(r"\b(?:long\s+)?leasehold\b", text, re.I) else None)

    out["tenant"] = _first([
        r"(?:Tenant|Lessee)\s*(?:\||:|-)?\s*([^|•]{2,110}?)(?=\s+(?:Lease|Term|Rent|Trading|Company|£)|[.;]|$)",
        r"(?:fully\s+)?let to\s+([^.;]{2,110}?)(?=\s+(?:on|for|at a rent|producing|paying)|[.;]|$)",
    ], text)
    out["lease_term"] = _first([
        r"(?:lease|tenancy)[^.;]{0,90}?for\s+(?:a\s+term\s+of\s+)?(\d+(?:\.\d+)?\s+years?)",
        r"\bTerm\s*(?:\||:|-)?\s*(\d+(?:\.\d+)?\s+years?)",
    ], text)
    out["lease_start"] = _first([
        r"(?:from|commencing|commenced)\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Start\s*(?:\||:|-)?\s*([^|;]{6,35})",
    ], text)
    out["lease_expiry"] = _first([
        r"(?:expir(?:y|es|ing)|until)\s*(?:on\s*)?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})",
        r"Lease\s+Expir(?:y|es)\s*(?:\||:|-)?\s*([^|;]{6,35})",
    ], text)
    out["break_clause"] = _first([
        r"(?:tenant(?:'s)?|landlord(?:'s)?)?\s*break(?:\s+clause|\s+option)?\s*(?:\||:|-|on)?\s*([^.;|]{4,120})",
        r"break\s+date\s*(?:\||:|-)?\s*([^.;|]{4,70})",
    ], text)
    out["rent_review"] = _first([
        r"rent review(?:s)?\s*(?:\||:|-)?\s*([^.;|]{4,120})",
        r"(rising to\s+£[\d,]+[^.;]{0,80})",
    ], text)

    out["epc"] = _extract_epc(text)
    out["rateable_value"] = _amount([
        r"(?:Rateable Value|RV)\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["area_sqft"], out["area_sqm"] = _extract_area(text)
    out["fri"] = True if re.search(r"\b(?:full repairing and insuring|FRI)\b", text, re.I) else None

    if re.search(r"\bNot\s+Elected\s+for\s+VAT\b", text, re.I):
        out["vat"] = "Not elected"
    elif re.search(r"VAT\s+(?:is\s+)?not\s+(?:applicable|payable)|not\s+subject\s+to\s+VAT|VAT[- ]free", text, re.I):
        out["vat"] = "Not applicable"
    elif re.search(r"VAT\s+(?:is\s+)?(?:applicable|payable)|subject\s+to\s+VAT|plus\s+VAT", text, re.I):
        out["vat"] = "Applicable"
    elif re.search(r"option(?:ed)?\s+to\s+tax|opted\s+for\s+VAT", text, re.I):
        out["vat"] = "Option to tax"
    else:
        out["vat"] = None
    out["togc"] = True if re.search(r"\bTOGC\b|transfer of a business as a going concern", text, re.I) else None

    out["service_charge"] = _amount([
        r"Service\s+Charge(?:\s+payable)?\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["ground_rent"] = _amount([
        r"Ground\s+Rent\s*(?:\||:|-)?\s*£\s*([\d,]+(?:\.\d+)?)",
    ], text)
    out["planning_use"] = _first([
        r"(?:Use\s+Class|Planning\s+Use|Class\s+E)\s*(?:\||:|-)?\s*([^.;|]{2,100})",
    ], text)
    if re.search(r"vacant possession|\bVACANT\b|\bvacant\b", text, re.I):
        out["occupation"] = "Vacant / vacant possession"
    elif out.get("tenant") or out.get("rent"):
        out["occupation"] = "Tenanted"
    else:
        out["occupation"] = None
    out["legal_pack"] = True if re.search(r"\blegal pack\b|legal documents", text, re.I) else None

    out["desc"] = text[:6500]
    return out


def merge_enrichment(row, facts):
    out = dict(row or {})
    facts = facts or {}
    # Explicit "Refer to Auctioneer" must clear a contaminated guide inherited
    # from related-lot boilerplate or an earlier generic parser.
    if facts.get("guide_status") == "Refer to Auctioneer":
        out["guide"] = None
        out["guide_status"] = "Refer to Auctioneer"

    for k, v in facts.items():
        if v in (None, ""):
            continue
        if k == "address" and out.get("address"):
            old = str(out["address"]).lower()
            contaminated = any(x in old for x in BOILERPLATE) or len(str(out["address"])) > 220
            if contaminated:
                out[k] = v
        elif k == "desc":
            if len(str(v)) > len(str(out.get(k) or "")):
                out[k] = v
        elif k == "guide" and facts.get("guide_status") == "Refer to Auctioneer":
            continue
        else:
            out[k] = v
    return out
'''

TESTS = r'''from collector_enrichment import extract_particulars, merge_enrichment


def test_auction_house_rich_lease_fields_and_clean_h1():
    html='''<html><main><h1>102-104 High Street, Redcar, Cleveland, TS10 3DL</h1>
    <div>Guide | £130,000</div><p>Retail investment let at £20,000 pa.</p>
    <p>Lease for a term of 12 years commencing 1 January 2025.</p>
    <p>Tenant break clause 1 January 2031. EPC Rating C (63).</p>
    <p>Rateable Value £18,500. Floor Area approximately 3,250 sq ft. FRI lease.</p></main></html>'''
    f=extract_particulars(html,"Auction House London")
    assert f["address"]=="102-104 High Street, Redcar, Cleveland, TS10 3DL"
    assert f["guide"]==130000
    assert f["rent"]==20000
    assert f["lease_term"]=="12 years"
    assert "2031" in f["break_clause"]
    assert f["epc"]=="C (63)"
    assert f["rateable_value"]==18500
    assert f["area_sqft"]==3250
    assert f["fri"] is True


def test_bond_wolfe_financial_and_tenancy_fields():
    html='''<html><main><h1>33-35 Cape Hill, Smethwick, B66 4RX</h1>
    <p>Guide Price £175,000</p><p>Current rental income £19,800 per annum.</p>
    <p>Tenant: Example Retail Limited. Lease for 10 years from 24 June 2024.</p>
    <p>Rent review 24 June 2029. EPC B (45). Freehold.</p></main></html>'''
    f=extract_particulars(html,"Bond Wolfe")
    assert f["guide"]==175000
    assert f["rent"]==19800
    assert f["tenant"]=="Example Retail Limited"
    assert f["lease_term"]=="10 years"
    assert f["tenure"]=="Freehold"
    assert f["epc"]=="B (45)"


def test_acuitus_scope_vat_epc_area_and_related_lot_contamination():
    html='''<html><main><h1>13 Stonehills, Welwyn Garden City, AL8 6ND</h1>
    <p>Freehold Former Bank Opportunity. Approx. 421.20 sq. m. (4,534 sq. ft.).</p>
    <p>Lot 26 Guide* Refer to Auctioneer</p><p>Tenure Freehold.</p>
    <p>VAT Not Elected for VAT</p><p>EPC Band E.</p>
    <h2>You may also be interested in</h2><p>Guide £850,000 EPC Band C.</p></main></html>'''
    f=extract_particulars(html,"Acuitus")
    assert f["guide"] is None
    assert f["guide_status"]=="Refer to Auctioneer"
    assert f["tenure"]=="Freehold"
    assert f["vat"]=="Not elected"
    assert f["epc"]=="E"
    assert abs(f["area_sqft"]-4534)<1
    assert abs(f["area_sqm"]-421.2)<0.1
    out=merge_enrichment({"guide":850000,"address":"13 Stonehills, Welwyn Garden City, AL8 6ND"},f)
    assert out["guide"] is None


def test_total_area_and_vat_applicable():
    html='''<main><h1>Former Wilko, 33-42 Fawcett Street, Sunderland, SR1 1RU</h1>
    <p>Total floor area of approximately 10,233.60 sq m (110,154 sq ft).</p>
    <p>VAT is applicable to this lot. EPC Band D. Tenure Freehold.</p></main>'''
    f=extract_particulars(html,"Acuitus")
    assert f["epc"]=="D"
    assert f["vat"]=="Applicable"
    assert abs(f["area_sqft"]-110154)<1
    assert abs(f["area_sqm"]-10233.6)<0.1


def test_service_charge_ground_rent_and_togc():
    html='''<main><h1>Unit 4 Example House, Leeds LS1 1AA</h1>
    <p>Leasehold. Service Charge £2,450 per annum. Ground Rent £250 pa.</p>
    <p>Sale is intended to be treated as a TOGC. EPC Rating B (42).</p></main>'''
    f=extract_particulars(html)
    assert f["service_charge"]==2450
    assert f["ground_rent"]==250
    assert f["togc"] is True
    assert f["epc"]=="B (42)"


def test_historical_rent_not_mistaken_for_current():
    html='''<main><h1>The Vaults, Manor Road, Chatham, ME4 6HW</h1>
    <p>Vacant. Previously let for £25,000 per annum. ERV £28,000 pa.</p></main>'''
    f=extract_particulars(html)
    assert f["rent"] is None
    assert f["erv"]==28000
'''

Path('collector_enrichment.py').write_text(MODULE, encoding='utf-8')
Path('tests/test_collector_enrichment.py').write_text(TESTS, encoding='utf-8')

app_path = Path('app.py')
s = app_path.read_text(encoding='utf-8')

old = '''def _enrich_exact_rows(rows, source_name, limit=220):
    out=[dict(r) for r in (rows or [])]
    targets=[i for i,r in enumerate(out) if r.get("url")][:limit]
    def one(i):
        r=out[i]
        try:
            facts=extract_particulars(fetch(r["url"]),source_name,r["url"])
            return i,merge_enrichment(r,facts)
        except Exception:
            return i,r
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures=[ex.submit(one,i) for i in targets]
        for f in as_completed(futures):
            i,r=f.result(); out[i]=r
    return out
'''
new = '''def _enrich_exact_rows(rows, source_name=None, limit=260):
    """Run the same exact-page schema across every auction source during refresh."""
    out=[dict(r) for r in (rows or [])]
    targets=[i for i,r in enumerate(out) if r.get("url") and not any(x in (r.get("url") or "") for x in ("/find-a-property/?clear=y","/property-search","/auctions/live-stream/"))][:limit]
    def one(i):
        r=out[i]
        try:
            actual_source=r.get("source") or source_name or ""
            facts=extract_particulars(fetch(r["url"]),actual_source,r["url"])
            return i,merge_enrichment(r,facts)
        except Exception:
            return i,r
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures=[ex.submit(one,i) for i in targets]
        for f in as_completed(futures):
            i,r=f.result(); out[i]=r
    return out
'''
if old not in s:
    raise SystemExit('universal _enrich_exact_rows anchor not found')
s=s.replace(old,new,1)

old = '''        try: rows=fn()
        except Exception: rows=[]
        if rows:
            if source=="Bond Wolfe":
                rows=_enrich_exact_rows(rows,"Bond Wolfe")
            if source=="Auction House Regional":
'''
new = '''        try: rows=fn()
        except Exception: rows=[]
        if rows:
            # Every discovered exact listing passes through the same structured
            # investment-fact parser before it is persisted into the snapshot.
            rows=_enrich_exact_rows(rows,source)
            if source=="Auction House Regional":
'''
if old not in s:
    raise SystemExit('merge catalogue universal enrichment anchor not found')
s=s.replace(old,new,1)

old = '''        return dict(source=source,lot=lot,date=date,address=address or 'Property',guide=guide,rent=rent,tenure=tenure,vat='UNKNOWN',url=url,desc=text[:1000],image=img)
'''
new = '''        base=dict(source=source,lot=lot,date=date,address=address or 'Property',guide=guide,rent=rent,tenure=tenure,vat='UNKNOWN',url=url,desc=text[:1000],image=img)
        return merge_enrichment(base,extract_particulars(raw,source,url))
'''
if old not in s:
    raise SystemExit('v654 exact row enrichment anchor not found')
s=s.replace(old,new,1)

old = '''    if p.get("fri") is True:
        f["Repairing"]="FRI"
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'
'''
new = '''    if p.get("fri") is True:
        f["Repairing"]="FRI"
    structured_vat=str(p.get("vat") or "").strip()
    if structured_vat and structured_vat.upper()!="UNKNOWN":
        f["VAT"]=structured_vat
        if structured_vat.lower() in ("not applicable","not elected"):
            chips.append("VAT "+structured_vat.upper())
        elif structured_vat.lower()=="applicable":
            chips.append("VAT APPLICABLE")
        else:
            chips.append("VAT VERIFY")
    if p.get("togc") is True:
        f["TOGC"]="Mentioned"
        chips.append("TOGC")
    if p.get("service_charge") is not None:
        f["Service charge"]=f'£{p["service_charge"]:,.0f} p.a.'
    if p.get("ground_rent") is not None:
        f["Ground rent"]=f'£{p["ground_rent"]:,.0f} p.a.'
    if p.get("planning_use"):
        f["Planning / use"]=str(p["planning_use"])
    if p.get("occupation"):
        f["Occupation"]=str(p["occupation"])
    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'
'''
if old not in s:
    raise SystemExit('structured display anchor not found')
s=s.replace(old,new,1)

app_path.write_text(s, encoding='utf-8')
print('Universal listing enrichment patch applied')
