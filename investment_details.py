"""Shared Auction Sniper investment presentation, extracted from the established board.

No Streamlit import, network calls or collector execution. Both frontends use this
same evidence interpretation. Reletting scores remain indicative heuristics.
"""
import re
import html

def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _source_text(p):
    """
    Render-path safe: use only data already captured for the property.
    Never fetch exact property pages while building the board.
    """
    parts=[
        p.get("desc"),
        p.get("address"),
        p.get("tenure"),
        p.get("vat"),
        p.get("legal_text"),
        p.get("rent_evidence"),
        p.get("previous_rent_evidence"),
        p.get("erv_evidence"),
    ]
    return norm(" ".join(str(x or "") for x in parts))

def _parse_date_any(s):
    from datetime import datetime
    for fmt in ("%d.%m.%Y","%d/%m/%Y","%d-%m-%Y","%d %B %Y","%d %b %Y"):
        try: return datetime.strptime(norm(s),fmt).date()
        except Exception: pass
    return None

def _remaining_years(s):
    from datetime import date
    d=_parse_date_any(s)
    return None if not d else max(0,(d-date.today()).days/365.2425)

SAVILLS_VERIFIED_AREAS = {
    "Lot 73": (None,None),
    "Lot 75": (12082,1122.00),
    "Lot 76": (2809,260.94),
    "Lot 77": (1103,102.47),
    "Lot 78": (7749,719.88),
    "Lot 79": (7715,716.74),
    "Lot 81": (1862,172.98),
    "Lot 83": (1356,125.98),
    "Lot 84": (11634,1080.90),
    "Lot 87": (2551,236.99),
    "Lot 96": (3553,330.10),
    "Lot 98": (3423,318.00),
}

TOWN_RELETTING_BASE = {
    # Town/catchment is intentionally only 10% of the final reletting score.
    "bath":7.5, "beaconsfield":7.3, "west malling":6.5, "petworth":6.2,
    "enfield":6.3, "northampton":5.6, "hythe":5.3, "crewe":5.0,
    "hull":4.8, "barnsley":4.5, "carmarthen":4.4, "wallasey":4.3,
    "liscard":4.3, "alfreton":4.3, "mexborough":3.8, "haverfordwest":4.2,
}

# Verified address-level evidence. These are micro-market facts, not covenant scores.
# They are deliberately source/address-specific and never keyed by lot number alone.
RELETTING_EVIDENCE = {
    "tutt antiques, angel street, petworth": {
        "micro_pitch":3.2,
        "occupier_depth":3.4,
        "vacancy_evidence":3.0,
        "note":"Commercial use on a predominantly residential/period street; vacant and reliant on a relatively narrow independent/specialist occupier pool.",
        "hard_cap":4.4,
    },
    "unit 5b, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":4.2,
        "vacancy_evidence":5.0,
        "note":"Prime pedestrianised pitch, but 7,749 sq ft is a large retail quantum for the Barnsley occupier market.",
        "hard_cap":5.5,
    },
    "unit 5a, 10-18 queen street, barnsley": {
        "micro_pitch":7.4,
        "occupier_depth":5.5,
        "vacancy_evidence":5.2,
        "note":"Prime pedestrianised pitch and materially smaller 1,862 sq ft unit, giving better occupier depth than Unit 5B.",
        "hard_cap":6.2,
    },
    "54-56 wallasey road, wallasey": {
        "micro_pitch":6.3,
        "occupier_depth":4.8,
        "vacancy_evidence":5.4,
        "note":"Established Liscard retail parade with national nearby occupiers, but weaker wider catchment and a double-width unit limit depth.",
        "hard_cap":5.8,
    },
    "unit 3, 15 john street, carmarthen": {
        "micro_pitch":6.0,
        "occupier_depth":4.5,
        "vacancy_evidence":4.8,
        "market_rent":45000,
        "market_rent_source":"proposed regear rent",
        "note":"Established retail pitch, but current £65,000 passing rent is materially above the £45,000 proposed regear evidence.",
        "hard_cap":5.2,
    },
    "15 red street, carmarthen": {
        "micro_pitch":5.8,
        "occupier_depth":4.2,
        "vacancy_evidence":4.6,
        "note":"Town-centre retail location, but 3,553 sq ft is a sizeable unit for Carmarthen and replacement demand is likely narrower.",
        "hard_cap":5.1,
    },
    "unit 5, the marsh, hythe": {
        "micro_pitch":5.8,
        "occupier_depth":5.0,
        "vacancy_evidence":5.0,
        "note":"Established local parade, but Hythe is a smaller occupier market; covenant strength is excluded from reletting.",
        "hard_cap":5.8,
    },
}

def _address_evidence(address):
    a=(address or "").lower().strip()
    for key,data in RELETTING_EVIDENCE.items():
        if key in a:
            return data
    return {}


def _town_base(address):
    a=(address or "").lower()
    for town,score in TOWN_RELETTING_BASE.items():
        if town in a:
            return score,town.title()
    return 5.0,"Neutral / unclassified town"

def _property_area(p,text):
    lot=p.get("lot")
    source=(p.get("source") or "").lower()
    if p.get("area_sqft"):
        try:
            sqft=float(p["area_sqft"])
            return sqft,sqft/10.7639
        except Exception:
            pass
    if p.get('canonical_snapshot'):
        if p.get('area_sqm'):
            sqm=float(p['area_sqm'])
            return sqm*10.7639,sqm
        return None,None
    # Verified lookup is Savills-only: never leak a Savills Lot 78 size onto another auctioneer's Lot 78.
    if "savills" in source and lot in SAVILLS_VERIFIED_AREAS and SAVILLS_VERIFIED_AREAS[lot][0]:
        return SAVILLS_VERIFIED_AREAS[lot]
    return _extract_floor_area(text)

def _extract_floor_area(text):
    """Return (sqft, sqm), normalised from either unit. Never returns a scalar."""
    sqft_vals=[]; sqm_vals=[]
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square feet)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 50<=v<=1_000_000: sqft_vals.append(v)
        except Exception: pass
    for m in re.finditer(r"([\d,]+(?:\.\d+)?)\s*(?:sq\s*m|sqm|m²|square metres|square meters)",text or "",re.I):
        try:
            v=float(m.group(1).replace(",",""))
            if 5<=v<=100_000: sqm_vals.append(v)
        except Exception: pass
    sqft=max(sqft_vals) if sqft_vals else None
    sqm=max(sqm_vals) if sqm_vals else None
    if sqft is None and sqm is not None: sqft=sqm*10.7639
    if sqm is None and sqft is not None: sqm=sqft/10.7639
    return sqft,sqm


def _unit_liquidity(p,facts,text):
    low=(text or "").lower(); score=5.0; pos=[]; risk=[]
    area,_sqm=_property_area(p,text)
    if area:
        if area<=1000: score+=1.2; pos.append(f"Small unit ({area:,.0f} sq ft) gives a broader occupier pool.")
        elif area<=2500: score+=0.6; pos.append(f"Manageable unit size ({area:,.0f} sq ft).")
        elif area<=5000: score-=0.2; risk.append(f"Mid-large unit ({area:,.0f} sq ft) narrows occupier depth.")
        elif area<=10000: score-=1.2; risk.append(f"Large unit ({area:,.0f} sq ft) materially narrows occupier demand.")
        else: score-=2.0; risk.append(f"Very large unit ({area:,.0f} sq ft) has limited occupier depth.")
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        score-=1.0; risk.append("Specialist configuration reduces replacement-tenant flexibility.")
    if any(x in low for x in ("parking","car park","service yard","loading bay")):
        score+=0.4; pos.append("Parking/loading improves usability.")
    return max(1.0,min(10.0,score)),area,pos[:3],risk[:3]


def _pitch_evidence(text):
    low=text.lower(); score=5.0; pos=[]; risk=[]; evidence=0
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","busy high street","prominent corner","town centre","city centre","high footfall")):
        score+=0.7; evidence+=1; pos.append("Particulars indicate a stronger/prominent pitch.")
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","edge of town","limited footfall","secondary retail")):
        score-=0.9; evidence+=1; risk.append("Particulars indicate a secondary/weaker pitch.")
    return max(1.0,min(10.0,score)),pos,risk,evidence

def _rental_stress(p,text):
    rent=p.get("rent"); vals=[]
    for label,pat in [("Proposed rent",r"(?:proposed rent|new rent|regear rent)\s*(?:of|at)?\s*£([\d,]+)"),("ERV",r"\bERV\b\s*(?:of|at)?\s*£([\d,]+)"),("Market rent",r"(?:estimated rental value|market rent)\s*(?:of|at)?\s*£([\d,]+)")]:
        for m in re.finditer(pat,text,re.I):
            try:
                v=float(m.group(1).replace(",",""))
                if 500<=v<=5_000_000: vals.append((v,label))
            except: pass
    if not rent or not vals: return None,None,None
    mr,label=min(vals,key=lambda x:x[0]); return mr,(rent-mr)/rent*100,label

def _reletting_assessment(p,facts,text):
    """
    Reletting means: existing tenant disappears tomorrow.

    Score components:
      25% immediate commercial pitch
      20% local occupier depth
      20% unit size/configuration liquidity
      15% vacancy/letting evidence
      10% rent sustainability
      10% town/catchment strength

    Covenant strength is deliberately excluded.
    """
    address=p.get("address") or ""
    low=(text or "").lower()
    ev=_address_evidence(address)
    town_score,town_name=_town_base(address)
    sqft,sqm=_property_area(p,text)

    # 1) Immediate pitch.
    pitch=5.0
    pitch_reason="No strong micro-pitch evidence captured."
    if any(x in low for x in ("prime retail pitch","principal pedestrianised","prime pedestrianised","high footfall","main shopping")):
        pitch=7.2; pitch_reason="Particulars support a strong established commercial pitch."
    elif any(x in low for x in ("popular parade","prominent pitch","town centre","city centre","prominent corner")):
        pitch=6.0; pitch_reason="Established/prominent commercial pitch."
    if any(x in low for x in ("secondary pitch","secondary parade","tertiary","limited footfall")):
        pitch=3.8; pitch_reason="Secondary/weaker commercial pitch."
    if ev.get("micro_pitch") is not None:
        pitch=ev["micro_pitch"]; pitch_reason=ev.get("note",pitch_reason)

    # Residential/isolation signals create a genuine micro-pitch penalty.
    residential_context=any(x in low for x in (
        "predominantly residential","mainly residential","residential street",
        "surrounded by residential","amongst residential"
    ))
    if residential_context:
        pitch=min(pitch,3.5)
        pitch_reason="Commercial premises within a substantially residential context."

    # 2) Occupier depth.
    occupier=5.0
    if any(x in low for x in ("national retailers","range of national retailers","principal retail amenity","main shopping")):
        occupier=6.1
    if any(x in low for x in ("small market town","village","rural location")):
        occupier=4.0
    if ev.get("occupier_depth") is not None:
        occupier=ev["occupier_depth"]

    # 3) Unit liquidity: size is a major input.
    unit=5.0
    unit_reason="Size/configuration not sufficiently evidenced."
    if sqft:
        if sqft<=750:
            unit=7.8; unit_reason=f"Very small unit ({sqft:,.0f} sq ft): broad potential occupier pool."
        elif sqft<=1500:
            unit=7.0; unit_reason=f"Small unit ({sqft:,.0f} sq ft): comparatively flexible."
        elif sqft<=3000:
            unit=6.0; unit_reason=f"Manageable unit ({sqft:,.0f} sq ft)."
        elif sqft<=5000:
            unit=4.8; unit_reason=f"Larger unit ({sqft:,.0f} sq ft): narrower replacement pool."
        elif sqft<=10000:
            unit=3.4; unit_reason=f"Large unit ({sqft:,.0f} sq ft): materially narrower occupier pool."
        else:
            unit=2.5; unit_reason=f"Very large unit ({sqft:,.0f} sq ft): specialist/deep occupier demand required."
    if any(x in low for x in ("care home","cinema","church","nightclub","petrol station","department store")):
        unit=max(1.0,unit-1.0)
        unit_reason+=" Specialist configuration adds friction."
    if any(x in low for x in ("parking","car park","service yard","loading bay","rear loading")):
        unit=min(10.0,unit+0.4)

    # 4) Vacancy / letting evidence.
    vacancy=5.0
    vacancy_reason="No strong local letting/vacancy evidence captured."
    if "vacant" in low or "vacant possession" in low:
        vacancy=4.2
        vacancy_reason="Currently vacant: no existing occupation evidence supporting immediate demand."
    if any(x in low for x in ("long standing occupier","tenant in occupation","occupation for 10+ years","occupation 20+ years")):
        vacancy=5.5
        vacancy_reason="Long occupation provides some evidence that the unit can sustain commercial use."
    if ev.get("vacancy_evidence") is not None:
        vacancy=ev["vacancy_evidence"]

    # 5) Rent sustainability.
    market_rent,stress,stress_source=_rental_stress(p,text)
    if ev.get("market_rent") is not None:
        market_rent=float(ev["market_rent"])
        stress_source=ev.get("market_rent_source","market evidence")
        stress=((p.get("rent")-market_rent)/p.get("rent")*100) if p.get("rent") else None

    rent_support=5.0
    rent_reason="No independent/regear rental evidence captured; neutral assumption."
    if market_rent is not None and p.get("rent"):
        if stress>=30:
            rent_support=2.0
        elif stress>=20:
            rent_support=3.0
        elif stress>=10:
            rent_support=4.0
        elif stress>=-10:
            rent_support=6.0
        else:
            rent_support=6.5
        rent_reason=f"{stress_source.title()} £{market_rent:,.0f} versus passing rent £{p['rent']:,.0f} ({stress:.0f}% stress)."

    # 6) Town/catchment.
    # Only 10%: an affluent town cannot rescue a poor unit/pitch.
    score=(0.25*pitch + 0.20*occupier + 0.20*unit +
           0.15*vacancy + 0.10*rent_support + 0.10*town_score)

    # Hard caps: these are deliberately non-linear.
    caps=[]
    if residential_context:
        caps.append((4.4,"Predominantly residential micro-location caps reletting at DIFFICULT."))
    if sqft and sqft>10000 and occupier<6.0:
        caps.append((4.5,"Very large unit in a limited occupier market caps reletting at DIFFICULT."))
    elif sqft and sqft>7500 and town_score<5.5:
        caps.append((5.2,"Large unit in a weaker regional market prevents a GOOD reletting rating."))
    if ("vacant" in low or "vacant possession" in low) and pitch<4.5:
        caps.append((4.3,"Vacant property on a weak/non-core pitch has prolonged-void risk."))
    if stress is not None and stress>=30:
        caps.append((4.8,"Passing rent is >30% above evidenced alternative rent."))
    if ev.get("hard_cap") is not None:
        caps.append((float(ev["hard_cap"]),ev.get("note","Address-level market evidence imposes a cap.")))

    for cap,_reason in caps:
        score=min(score,cap)

    score=max(1.0,min(10.0,score))
    label=("VERY STRONG" if score>=8.0 else
           "GOOD" if score>=6.5 else
           "MODERATE" if score>=5.0 else
           "DIFFICULT" if score>=3.5 else
           "HIGH RISK")

    evidence_points=sum([
        1 if sqft else 0,
        1 if ev else 0,
        1 if market_rent is not None else 0,
        1 if pitch_reason!="No strong micro-pitch evidence captured." else 0,
        1 if vacancy_reason!="No strong local letting/vacancy evidence captured." else 0,
    ])
    confidence="HIGH" if evidence_points>=4 else "MEDIUM" if evidence_points>=2 else "LOW"

    return {
        "score":score,"label":label,"confidence":confidence,
        "town_score":town_score,"town_name":town_name,
        "pitch_score":pitch,"occupier_score":occupier,"unit_score":unit,
        "vacancy_score":vacancy,"rent_score":rent_support,
        "sqft":sqft,"sqm":sqm,
        "market_rent":market_rent,"rent_stress":stress,"market_rent_source":stress_source,
        "pitch_reason":pitch_reason,"unit_reason":unit_reason,
        "vacancy_reason":vacancy_reason,"rent_reason":rent_reason,
        "caps":[r for _c,r in caps],
    }


def _investment_interpretation(f):
    notes=[]; yrs=f.get("_remaining_years")
    if "national" in f.get("Covenant","").lower(): notes.append("Recognised national/operator covenant.")
    elif f.get("Tenant"): notes.append("Tenant identified; financial covenant strength still needs verification.")
    if yrs is not None:
        if yrs<4: notes.append(f"Relatively short income: about {yrs:.1f} years to expiry.")
        elif yrs<7: notes.append(f"Medium-short income: about {yrs:.1f} years to expiry.")
        else: notes.append(f"About {yrs:.1f} years of contractual income, subject to any break.")
    if "outstanding" in f.get("Rent review / steps","").lower(): notes.append("Outstanding rent review may provide rental uplift; outcome is unproven.")
    if f.get("Break clause"): notes.append("Break clause may shorten the effective income term; exact date/party shown above.")
    if not f.get("Passing rent") and "vacant" in f.get("Occupation","").lower(): notes.append("No passing income: value depends on reletting/development prospects.")
    return notes[:4]

def _investment_facts(p):
    text=_source_text(p); low=text.lower(); f={}; chips=[]
    tenure=p.get("tenure") or ("Freehold" if "freehold" in low else "Leasehold" if "leasehold" in low else None)
    if tenure: f["Tenure"]=tenure

    tenant=p.get("tenant")
    if not tenant and not p.get("canonical_snapshot"):
        for pat in [
            r"(?:fully\s+)?let to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|\s+at\s+(?:a\s+)?rent|[.;])",
            r"leased to\s+([^.;\n]{2,100}?)(?=\s+on\s+(?:a\s+)?\d|\s+paying|[.;])",
            r"tenant[:\s]+([^.;\n]{2,90})"]:
            m=re.search(pat,text,re.I)
            if m:
                tenant=norm(m.group(1)).strip("'\"“”")[:90]
                if tenant: break
    if tenant: f["Tenant"]=tenant

    # Prefer structured exact-page collector facts over re-parsing prose.
    if p.get("lease_term"):
        f["Lease term"]=str(p["lease_term"])
    if p.get("lease_start"):
        f["Lease start"]=str(p["lease_start"])
    if p.get("lease_expiry"):
        f["Lease expiry"]=str(p["lease_expiry"])
    if p.get("break_clause"):
        f["Break clause"]=str(p["break_clause"])
    if p.get("rent_review"):
        f["Rent review / steps"]=str(p["rent_review"])
    if p.get("epc"):
        f["EPC"]=str(p["epc"])
        chips.append("EPC "+str(p["epc"]))
    if p.get("rateable_value"):
        f["Rateable value"]=f'£{p["rateable_value"]:,.0f}'
    if p.get("fri") is True:
        f["Repairing"]="FRI"
    if p.get("property_type"): f["Property type"]=str(p["property_type"])
    if p.get("site_area_acres"): f["Site area"]=f'{p["site_area_acres"]:,.2f} acres'
    if p.get("parking"): f["Parking"]=str(p["parking"])
    if p.get("break_status"): f["Break status"]=str(p["break_status"])
    if p.get("covenant_rating"):
        cv=str(p["covenant_rating"])
        if p.get("covenant_risk"): cv+=f' ({p["covenant_risk"]})'
        f["Covenant"]=cv
    if p.get("covenant_turnover"): f["Tenant turnover"]=str(p["covenant_turnover"])
    if p.get("guarantors"): f["Lease security"]=str(p["guarantors"])
    if p.get("pitch"): f["Pitch"]=str(p["pitch"])
    if p.get("nearby_occupiers"): f["Nearby occupiers"]=str(p["nearby_occupiers"])
    if p.get("listed_status"): f["Listed status"]=str(p["listed_status"])

    # Context-sensitive badges: show what changes the investment case, not duplicate tenure.
    for flag,label in (("development_potential","DEVELOPMENT"),("asset_management","ASSET MANAGEMENT"),
                       ("refurbishment","REFURBISHMENT"),("residential_conversion","RESIDENTIAL CONVERSION")):
        if p.get(flag) and label not in chips: chips.append(label)
    if p.get("listed_status") and str(p["listed_status"]).upper() not in chips: chips.append(str(p["listed_status"]).upper())
    if p.get("break_status") and "BREAK PASSED" not in chips: chips.append("BREAK PASSED")
    if p.get("guarantors") and "GUARANTORS" not in chips: chips.append("GUARANTORS")
    if p.get("covenant_risk") and "low risk" in str(p["covenant_risk"]).lower() and "LOW-RISK COVENANT" not in chips: chips.append("LOW-RISK COVENANT")
    if p.get("rent_review") and "rpi" in str(p["rent_review"]).lower() and "RPI REVIEW" not in chips: chips.append("RPI REVIEW")
    if p.get("property_type") and str(p["property_type"]).lower()=="mixed use" and "MIXED USE" not in chips: chips.append("MIXED USE")
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
    if p.get("rent_status"): f["Rent status"]=p["rent_status"]
    if p.get("previous_rent"):
        f["Previous / historic rent"]=f'£{p["previous_rent"]:,.0f} p.a. — NOT current income'
        chips.append("HISTORIC RENT")
    if p.get("erv"):
        f["ERV / market-rent evidence"]=f'£{p["erv"]:,.0f} p.a. — NOT passing rent'
        chips.append(f'ERV £{p["erv"]:,.0f} p.a.')
    if p.get("legal_text"):
        f["Legal documents scanned"]="Yes — extracted text used in analysis"
        chips.append("LEGAL TEXT SCANNED")
    elif p.get("legal_pack_url"):
        f["Legal pack"]="Link found — text not yet extractable"

    m=re.search(r"(\d+(?:\.\d+)?)\s*year\s+(?:full\s+repairing\s+and\s+insuring\s+|FRI\s+)?lease",text,re.I)
    if m and not p.get("canonical_snapshot"): f["Original lease term"]=m.group(1)+" years"
    m=re.search(r"(?:lease\s+)?expir(?:y|ing|es)\s*(?:on\s*)?(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})",text,re.I)
    if m and not p.get("canonical_snapshot"):
        expiry=m.group(1); f["Lease expiry"]=expiry; yrs=_remaining_years(expiry)
        if yrs is not None:
            f["Term remaining"]=f"{yrs:.1f} years"; f["_remaining_years"]=yrs
            if yrs<=10: chips.append(f"{yrs:.1f} YRS LEFT")

    if re.search(r"\bFRI\b|full repairing and insuring",text,re.I): f["Repairing"]="FRI"; chips.append("FRI")
    elif re.search(r"\bIRI\b|internal repairing",text,re.I): f["Repairing"]="IRI"

    for pat in [r"((?:tenant|landlord)[^.;]{0,35}break[^.;]{0,100})",r"((?:break clause|option to determine)[^.;]{0,120})"]:
        m=re.search(pat,text,re.I)
        if m and not p.get("canonical_snapshot"): f["Break clause"]=norm(m.group(1))[:140]; chips.append("BREAK"); break

    m=re.search(r"((?:\d{4}\s+)?rent review[^.;]{0,120}(?:outstanding)?|outstanding rent review[^.;]{0,120}|rising to\s+£?[\d,]+[^.;]{0,100})",text,re.I)
    if m and not p.get("rent_review"):
        rr=norm(m.group(1)); f["Rent review / steps"]=rr[:140]
        if "outstanding" in rr.lower(): chips.append("RENT REVIEW OUTSTANDING")

    m=re.search(r"(\d+)\s*months?\s+deposit",text,re.I)
    if m: f["Rent deposit"]=m.group(1)+" months"
    m=re.search(r"(\d+)\s*months?\s+(?:initial\s+)?rent[- ]free",text,re.I)
    if m: f["Rent free"]=m.group(1)+" months"

    if re.search(r"VAT[- ]free|VAT\s+is\s+not\s+applicable|VAT\s+not\s+applicable|not subject to VAT",text,re.I): f["VAT"]="Not applicable / VAT-free"; chips.append("VAT-FREE")
    elif re.search(r"plus VAT|VAT applicable|subject to VAT|VAT will be payable",text,re.I): f["VAT"]="Applicable"; chips.append("VAT")
    elif re.search(r"option(?:ed)? to tax|opted for VAT",text,re.I): f["VAT"]="Option to tax mentioned"; chips.append("VAT VERIFY")
    if re.search(r"\bTOGC\b|transfer of a business as a going concern",text,re.I): f["TOGC"]="Mentioned"; chips.append("TOGC")

    if p.get("canonical_snapshot"):
        occupation=str(p.get("occupation") or "")
        if occupation: f["Occupation"]=occupation
        if "part" in occupation.lower() and "vacant" in occupation.lower(): chips.append("PART VACANT")
        elif occupation.lower().startswith("vacant"): chips.append("VACANT")
    elif re.search(r"vacant possession|\bvacant\b",text,re.I): f["Occupation"]="Vacant / vacant possession"; chips.append("VACANT")
    elif tenant: f["Occupation"]="Tenanted"
    if re.search(r"download the legal pack|legal documents|legal pack",text,re.I): f["Legal pack"]="Available / referenced"; chips.append("LEGAL PACK")

    national=("domino","dp realty","tesco","sainsbury","boots","superdrug","co-op","nationwide","hsbc","barclays","lloyds","natwest","coral","william hill","greggs","subway","costa","starbucks","mcdonald","aldi","lidl","b&m","poundland","british red cross","british heart foundation","holland & barrett","holland and barrett")
    if tenant and not p.get("covenant_rating") and not f.get("Covenant"):
        if any(n in tenant.lower() for n in national):
            f["Covenant"]="Recognised national operator / established organisation"
            chips.append("STRONGER COVENANT")
        else:
            f["Covenant"]="Tenant identified — strength not yet verified"

    if p.get("guide") and p.get("rent"):
        y=100*p["rent"]/p["guide"]; f["GIY at guide"]=f"{y:.1f}%"; f["10% ceiling"]=f'£{p["rent"]/0.10:,.0f}'
    rel=_reletting_assessment(p,f,text)
    from property_summary import specialist_use, inaccessible_upper_parts
    special = specialist_use(p)
    if special:
        rel['unit_reason'] = f"{special} use: replacement demand, permitted use and fit-out costs require evidence; floor area alone does not establish flexibility."
    if inaccessible_upper_parts(p):
        f['Upper accommodation'] = 'Former accommodation has no access; independent lettability and income are not established'
    f["Reletting potential"]=f'{rel["score"]:.1f}/10 — {rel["label"]}'
    f["Reletting confidence"]=rel["confidence"]
    f["Immediate pitch"]=f'{rel["pitch_score"]:.1f}/10'
    f["Occupier depth"]=f'{rel["occupier_score"]:.1f}/10'
    f["Unit liquidity"]=f'{rel["unit_score"]:.1f}/10'
    f["Vacancy / letting evidence"]=f'{rel["vacancy_score"]:.1f}/10'
    f["Rent sustainability"]=f'{rel["rent_score"]:.1f}/10'
    f["Town / catchment"]=f'{rel["town_score"]:.1f}/10 — {rel["town_name"]}'
    chips.append(f'RELETTING {rel["label"]}')

    if rel.get("sqft"):
        f["Floor area"]=f'{rel["sqft"]:,.0f} sq ft / {rel["sqm"]:,.0f} sq m'
    if rel.get("market_rent") is not None:
        f["Evidenced re-letting rent"]=f'£{rel["market_rent"]:,.0f} p.a. ({rel["market_rent_source"]})'
        if rel.get("rent_stress") is not None:
            f["Passing-rent stress"]=f'{rel["rent_stress"]:.0f}%'
            f["10% value at re-letting rent"]=f'£{rel["market_rent"]/0.10:,.0f}'

    interpretation=_investment_interpretation(f)
    interpretation.append("Reletting: "+rel["unit_reason"])
    interpretation.append("Pitch: "+rel["pitch_reason"])
    if rel["caps"]:
        interpretation.append("Risk cap: "+rel["caps"][0])
    interpretation=interpretation[:7]
    f.pop("_remaining_years",None)

    # Remove synonyms/duplication before rendering. Headline tenure is intentionally
    # excluded because it already occupies its own metric box.
    raw=list(dict.fromkeys(chips))
    cleaned=[]
    seen_sem=set()
    for chip in raw:
        c=str(chip).strip()
        u=c.upper()
        if not c or u in {"FREEHOLD","LEASEHOLD","LONG LEASEHOLD"}:
            continue
        if u.startswith("VAT"):
            sem="VAT"
        elif u in {"BREAK","BREAK PASSED"}:
            sem="BREAK"
        elif u in {"LEGAL PACK","LEGAL TEXT SCANNED"}:
            sem="LEGAL"
        elif u.startswith("RELETTING "):
            sem="RELETTING"
        elif u in {"STRONGER COVENANT","LOW-RISK COVENANT"}:
            sem="COVENANT"
        else:
            sem=u
        if sem in seen_sem:
            # Prefer the more informative forms when encountered later.
            if sem=="BREAK" and u=="BREAK PASSED":
                cleaned=[x for x in cleaned if x.upper()!="BREAK"]
                cleaned.append(c)
            elif sem=="COVENANT" and u=="LOW-RISK COVENANT":
                cleaned=[x for x in cleaned if x.upper()!="STRONGER COVENANT"]
                cleaned.append(c)
            elif sem=="LEGAL" and u=="LEGAL TEXT SCANNED":
                cleaned=[x for x in cleaned if x.upper()!="LEGAL PACK"]
                cleaned.append(c)
            continue
        seen_sem.add(sem); cleaned.append(c)

    def chip_priority(c):
        u=c.upper()
        if any(x in u for x in ("DEVELOPMENT","ASSET MANAGEMENT","RESIDENTIAL CONVERSION","REFURBISHMENT","MIXED USE")): return 10
        if "YRS LEFT" in u or u in {"BREAK PASSED","GUARANTORS","RPI REVIEW"}: return 20
        if "COVENANT" in u: return 30
        if u=="VACANT" or "GRADE II" in u: return 40
        if u=="FRI" or u=="IRI": return 50
        if u.startswith("ERV "): return 60
        if u.startswith("VAT"): return 70
        if u.startswith("RELETTING "): return 80
        if u.startswith("LEGAL"): return 90
        return 65
    cleaned=sorted(cleaned,key=chip_priority)[:6]
    return f,cleaned,interpretation

def _research_links(p):
    import urllib.parse
    address=str(p.get("address") or "").strip()
    if not address: return ""
    qh=urllib.parse.quote(f'"{address}" property auction sold previous listing')
    qp=urllib.parse.quote(f'"{address}" commercial property')
    legal=(f'<a target="_blank" href="{html.escape(str(p.get("legal_pack_url")),quote=True)}">Legal pack / document ↗</a>' if p.get("legal_pack_url") else "")
    return ('<div class="research">'+legal
            +f'<a target="_blank" href="https://www.google.com/search?q={qh}">Sales / auction history ↗</a>'
            f'<a target="_blank" href="https://www.google.com/search?q={qp}">Previous listings ↗</a>'
            f'<a target="_blank" href="https://www.gov.uk/search-house-prices">Land Registry search ↗</a>'
            '</div>')

def _facts_html(p):
    facts,chips,interpretation=_investment_facts(p)
    if not facts: return ""
    ch="".join(f'<span class="chip">{html.escape(str(x))}</span>' for x in chips[:7])
    rows="".join(f'<div class="fact"><span>{html.escape(str(k))}</span><b>{html.escape(str(v))}</b></div>' for k,v in facts.items())
    read=""
    if interpretation:
        read="<div class='iread'><span>Investment read</span>"+"".join(f"<p>• {html.escape(n)}</p>" for n in interpretation)+"</div>"
    return f'<div class="chips">{ch}</div><details class="analysis"><summary>Investment details</summary><div class="factgrid">{rows}</div>{read}{_research_links(p)}</details>'


