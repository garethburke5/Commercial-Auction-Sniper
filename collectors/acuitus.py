import re
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .core import SourceResult, Lot, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .financials import guide_range
from .utils import soup, nearest_card, legal_pack

SOURCE="Acuitus"
BASE="https://www.acuitus.co.uk"
URL=BASE+"/find-a-property/?which=sales"



def _num(v):
    try: return float(str(v).replace(",", ""))
    except Exception: return None


def _section(text,name,next_names):
    tail="|".join(re.escape(x) for x in next_names)
    m=re.search(rf"{re.escape(name)}\s+(.+?)(?=(?:{tail})\s+|Tenancy & Accommodation|Contacts|Useful Links|$)",text or "",re.I)
    return norm(m.group(1)) if m else None


def _is_commercial_card(card):
    low=(card or "").lower()
    commercial=("retail","office","industrial","warehouse","mixed use","mixed-use","development","bank","restaurant","petrol station","ground rent","self storage","leisure","hotel","care home","commercial")
    if not any(x in low for x in commercial): return False
    pure_res=("shared ownership houses","residential only","residential investment")
    return not (any(x in low for x in pure_res) and not any(x in low for x in ("retail","office","industrial","warehouse","mixed use","mixed-use","commercial","development")))


def _property_image(ds, href):
    pm=re.search(r"/property/(\d+)/?",href,re.I)
    pid=pm.group(1) if pm else None
    scored=[]
    for img in ds.find_all("img"):
        raw=img.get("data-src") or img.get("data-lazy-src") or img.get("data-original") or img.get("src")
        if not raw: continue
        u=urljoin(href,raw)
        low=u.lower()
        if any(x in low for x in ("logo","favicon","icon","sprite","placeholder","avatar","social","acuitus-logo")): continue
        score=0
        if pid and re.search(rf"/uploads/[^/]*-{re.escape(pid)}/",low): score+=100
        if "/uploads/" in low: score+=20
        if any(x in low for x in ("1600x900","1200x","1024x","800x450")): score+=8
        if any(x in low for x in ("128x72","thumbnail","thumb")): score-=8
        alt=norm(img.get("alt") or "").lower()
        if any(x in alt for x in ("property","lot","building","street")): score+=4
        if score>0: scored.append((score,u))
    if not scored: return None
    scored.sort(key=lambda x:x[0],reverse=True)
    return scored[0][1]


def _area(text):
    pairs=(
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",
        r"([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)\s*\(?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",
    )
    m=re.search(pairs[0],text,re.I)
    if m: return _num(m.group(1)),_num(m.group(2))
    m=re.search(pairs[1],text,re.I)
    if m: return _num(m.group(2)),_num(m.group(1))
    m=re.search(r"(?:approximately|approx\.?|extending to|comprising)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|ft²)",text,re.I)
    if m:
        sqft=_num(m.group(1)); return sqft, round(sqft/10.7639,2) if sqft else None
    m=re.search(r"(?:approximately|approx\.?|extending to|comprising)?\s*([\d,]+(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|m²)",text,re.I)
    if m:
        sqm=_num(m.group(1)); return round(sqm*10.7639,2) if sqm else None, sqm
    return None,None


def _fallback_type(text):
    for pat,label in (
        (r"mixed[- ]use","Mixed use"),(r"retail|shop|high street","Retail"),(r"office","Office"),
        (r"industrial|warehouse|trade counter","Industrial"),(r"ground rent","Ground rent"),
        (r"hotel|hostel","Hotel"),(r"care home","Care facility"),(r"public house|\bpub\b","Pub"),
        (r"restaurant|cafe|takeaway","Restaurant / leisure"),(r"development site|development opportunity","Development"),
    ):
        if re.search(pat,text,re.I): return label
    return "Commercial"


def _rich_lot(href, card, card_fields=None):
    ds=soup(href,use_browser=False)
    main=ds.find("main") or ds
    # The source places tenure, description and tenancy OUTSIDE <main>.
    # Capture those exact-lot sections, excluding related properties and contacts.
    sections=[]
    for node in ds.select('.propinfo.info, .propinfo.tenancy'):
        section=BeautifulSoup(str(node),'lxml')
        for duplicate in section.select('.printonly'):duplicate.decompose()
        sections.append(section.get_text(' ',strip=True).replace('Property Information',''))
    headline=main.get_text(' ',strip=True).split('Interested?',1)[0]
    text=norm(' '.join([headline]+sections))
    combined=text
    facts={}
    for item in ds.select('main .specifics li'):
        label=item.find('span')
        if label:
            key=norm(label.get_text(' ',strip=True)).rstrip('*†')
            facts[key]=norm(item.get_text(' ',strip=True))[len(norm(label.get_text(' ',strip=True))):].strip()
    auction_date=_date(facts.get('Auction',''))
    if not auction_date:
        match=re.search(r'\bAuction\s+(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+20\d{2})',text,re.I)
        auction_date=_date(match.group(1)) if match else None
    if not auction_date or not ds.find('h1'):
        raise ValueError('Missing exact-lot auction date or property title')
    if card_fields and auction_date != _date(card_fields.get('Auction','')):
        raise ValueError('Catalogue/detail auction dates disagree')
    h1=ds.find("h1")
    address=norm(h1.get_text(" ",strip=True)) if h1 else None
    if not address:
        title=ds.find("title")
        address=norm(title.get_text(" ",strip=True)).split("|")[0] if title else href

    m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",combined,re.I)
    lotno="Lot "+m.group(1) if m else None
    guide_text=facts.get('Guide') or (card_fields or {}).get('Guide')
    guide=parse_guide('Guide '+guide_text) if guide_text else None
    guide_upper=guide_range('Guide '+guide_text)[1] if guide_text else None
    rent=None
    rm=re.search(r"£\s*([\d,]+(?:\.\d+)?)",facts.get('Rent',''),re.I)
    if rm: rent=_num(rm.group(1))
    elif not re.search(r"\bVacant\b",text[:2200],re.I): rent=parse_rent(combined)

    lp_url,lp_status=legal_pack(ds,href)
    lot=Lot(source=SOURCE,url=href,address=address,lot_number=lotno,auction_date=auction_date,
        image_url=_property_image(ds,href),image_is_primary=True,image_source_url=href,
        guide_price=guide,guide_price_upper=guide_upper,guide_price_text=guide_text,annual_rent=rent,
        tenure=parse_tenure(combined),vat_status=parse_vat(combined),legal_pack_status=lp_status,
        legal_pack_url=lp_url,status=_status(facts.get("Status") or (card_fields or {}).get("Status")),description=text[:9000])

    sector=_section(text,"Sector",["Auction Venue","Property Information","Location"])
    lot.property_type=sector[:120] if sector else _fallback_type(combined)
    tenure=_section(text,"Tenure",["Description","VAT","EPC","Tenancy & Accommodation"])
    if tenure:
        lot.tenure=parse_tenure(tenure) or lot.tenure
        gm=re.search(r"ground rent of\s*£\s*([\d,]+(?:\.\d+)?)\s*(?:pa|p\.a\.|per annum)",tenure,re.I)
        if gm: lot.ground_rent=_num(gm.group(1))
        exp=re.search(r"expiring in\s+(20\d{2}|21\d{2})",tenure,re.I)
        if exp: lot.lease_expiry=exp.group(1)

    lot.area_sqft,lot.area_sqm=_area(combined)
    # Table totals carry units in their headings, not beside each number.
    for table in ds.select('.propinfo.tenancy table'):
        headers=[norm(h.get_text(' ',strip=True)).lower() for h in table.select('thead th')]
        if not headers:
            headers=[norm(h.get_text(' ',strip=True)).lower() for h in table.select('tr')[0].find_all(['th','td'])]
        for tr in table.select('tr'):
            cells=[norm(c.get_text(' ',strip=True)) for c in tr.find_all(['td','th'])]
            if cells and cells[0].lower().startswith('total'):
                # Total rows use a colspan for Floor / Use.
                expanded=[]
                for c in tr.find_all(['td','th']):
                    expanded += [norm(c.get_text(' ',strip=True))]+['']*(int(c.get('colspan',1))-1)
                for i,h in enumerate(headers):
                    if i<len(expanded):
                        number=re.match(r'\(?([\d,]+(?:\.\d+)?)',expanded[i])
                        value=_num(number.group(1)) if number else None
                        if value and 'sq m' in h:lot.area_sqm=value
                        if value and 'sq ft' in h:lot.area_sqft=value
            if len(cells)>=7 and cells[0].lower()!='total' and re.search(r'years? from', ' '.join(cells),re.I):
                lot.tenancy_schedule.append(dict(zip(headers,cells)))
    if len(lot.tenancy_schedule)==1:
        entry=lot.tenancy_schedule[0]
        lot.tenant=entry.get('tenant')
        lot.lease_term=entry.get('term')
        lot.rent_review=entry.get('rent review')
    sm=re.search(r"([\d.]+)\s*acres?\b",combined,re.I)
    if sm: lot.site_area_acres=_num(sm.group(1))
    epc=re.search(r"\bEPC\s+(?:(?:Rating|Band)\s+)?([A-G])\b",combined,re.I)
    if epc: lot.epc=epc.group(1).upper()

    if re.search(r"VAT is not applicable|VAT free investment|VAT-free investment",combined,re.I): lot.vat_status="NOT APPLICABLE"
    elif re.search(r"VAT is applicable|elected for VAT",combined,re.I): lot.vat_status="APPLICABLE"

    if rent is not None:
        lot.occupation="Part-let / part-vacant" if re.search(r"\bpart(?:ly)?[- ]vacant|vacant (?:unit|floor|part)",combined,re.I) else "Tenanted"
    elif re.search(r"\bvacant(?: possession)?\b|offered with vacant possession",combined[:4500],re.I):
        lot.occupation="Vacant"
    elif re.search(r"Tenancy & Accommodation|Tenant\s+Term\s+Rent|\blet to\b|\bleased to\b",combined,re.I):
        lot.occupation="Tenanted"

    tenants=[]
    for tm in re.finditer(r"\b([A-Z][A-Z0-9 '&().-]{3,80}(?:LIMITED|LTD|PLC))\b",combined):
        name=norm(tm.group(1))
        if name not in tenants: tenants.append(name)
    if tenants and not lot.tenant: lot.tenant=" / ".join(tenants[:3])
    if not lot.tenant:
        tm=re.search(r"(?:let|leased) to\s+([A-Z][A-Za-z0-9 '&().,-]{2,80}?)(?:\s+on\s+|\s+for\s+|\s+at\s+|\.|,)",combined)
        if tm: lot.tenant=norm(tm.group(1))

    if re.search(r"asset management opportunit|asset management potential|repositioning opportunit|re-letting potential|reletting potential",combined,re.I): lot.asset_management=True
    if re.search(r"development potential|development opportunity|redevelop|subject to planning|planning permission|lapsed.*consent",combined,re.I): lot.development_potential=True
    if re.search(r"residential conversion|conversion to residential|upper floors.*residential|residential accommodation",combined,re.I): lot.residential_conversion=True
    if re.search(r"refurbish|refurbishment",combined,re.I): lot.refurbishment=True

    pm=re.search(r"(\d{1,4})\s+(?:car\s+)?parking spaces?",combined,re.I)
    if pm: lot.parking=f"{pm.group(1)} parking spaces"
    elif re.search(r"rear loading|parking|car park",combined,re.I): lot.parking="Parking/loading mentioned"

    situation=_section(text,"Situation",["Tenure","Description","VAT","EPC"])
    situation_text=situation or combined[:4500]
    if re.search(r"prominent|prime|city centre|town centre|high street|frontage",situation_text,re.I): lot.pitch="Prominent/central commercial location"
    near=re.search(r"Nearby occupiers include\s+(.+?)(?:\.|Tenure|Description|$)",situation_text,re.I)
    if near: lot.nearby_occupiers=norm(near.group(1))[:300]

    return lot.finalise()



def _date(value):
    value=re.sub(r'(\d)(?:st|nd|rd|th)\b',r'\1',norm(value),flags=re.I)
    for fmt in ('%d/%m/%Y','%d %B %Y','%d %b %Y'):
        try:return datetime.strptime(value,fmt).date().isoformat()
        except ValueError:pass
    return None


def _status(value):
    value=norm(value).upper()
    return {'AVAILABLE':'CURRENT','SOLD POST':'SOLD POST','SOLD PRIOR':'SOLD PRIOR',
            'SOLD':'SOLD','WITHDRAWN':'WITHDRAWN','WITHDRAWN PRIOR':'WITHDRAWN PRIOR','POSTPONED':'POSTPONED',
            'UNSOLD':'UNSOLD'}.get(value,'STATUS UNKNOWN')


def catalogue_cards(s):
    """Read the source's structured cards and published count, without date filters."""
    match=re.search(r'(\d+)\s*[-–]\s*(\d+)\s+of\s+(\d+)\s+properties',s.get_text(' ',strip=True),re.I)
    bounds=tuple(map(int,match.groups())) if match else None
    targets=[];seen=set()
    for a in s.select('a[href]'):
        address=a.select_one('.proplist-grid-address');stats=a.select_one('.proplist-grid-status')
        if not address or not stats:continue
        href=urljoin(BASE,a['href']).split('?',1)[0].rstrip('/')+'/'
        if not re.fullmatch(re.escape(BASE)+r'/property/\d+/',href):continue
        if href in seen:raise ValueError('Repeated catalogue lot link')
        seen.add(href)
        fields={norm(dt.get_text(' ',strip=True)).rstrip('*†'):norm(dt.find_next_sibling('dd').get_text(' ',strip=True))
                for dt in stats.find_all('dt') if dt.find_next_sibling('dd')}
        fields['address']=', '.join(address.stripped_strings)
        kind=a.select_one('.proplist-sector')
        fields['sector']=norm(kind.get_text(' ',strip=True)) if kind else ''
        targets.append((href,norm(a.get_text(' ',strip=True)),fields))
    complete=bool(bounds and bounds[0]==1 and bounds[1]==bounds[2]==len(targets))
    return targets,bounds[2] if bounds else None,complete


def _inspect(target):
    href,card,fields=target
    outcome={'url':href,'lot':fields.get('Lot'),'auction_date':_date(fields.get('Auction','')),'parsed':False}
    try:
        lot=_rich_lot(href,card,fields)
        if lot.status=='STATUS UNKNOWN':raise ValueError('Unrecognised source availability status')
        outcome['parsed']=True
        if lot.auction_date<date.today().isoformat():return None,{**outcome,'outcome':'past_auction'}
        from .publication_quality import commercial_decision
        # Inspect every card, including specialist commercial uses and pure residential.
        if commercial_decision(lot.to_dict()) is False:
            return None,{**outcome,'outcome':'classification_rejected','reason':'Pure residential; no current commercial asset evidenced'}
        return lot,{**outcome,'outcome':'mixed_use' if re.search('residential|mixed',fields.get('sector',''),re.I) else 'commercial'}
    except Exception as exc:
        return None,{**outcome,'outcome':'detail_failure','reason':f'{type(exc).__name__}: {exc}'}


def collect():
    try:
        s=soup(URL,use_browser=False)
        targets,expected,complete=catalogue_cards(s)
        if expected is not None and len(targets)<expected:
            # Reuse the source's own form: no price cap and no hard-coded sale.
            import requests
            from bs4 import BeautifulSoup
            form=s.find('form',attrs={'name':'filter'})
            fields={n['name']:n.get('value','') for n in form.select('input[name]')} if form else {}
            fields['perpage']='1000'
            response=requests.post(URL,data=fields,timeout=45);response.raise_for_status()
            s=BeautifulSoup(response.text,'lxml');targets,expected,complete=catalogue_cards(s)
        if not targets:
            pending=bool(re.search('full auction catalogue will be available',s.get_text(' ',strip=True),re.I))
            return SourceResult(SOURCE,'CATALOGUE PENDING' if pending else 'FAILED',[],
                'Source explicitly says catalogue is pending' if pending else 'No identifiable catalogue cards; zero is not verified',
                reconciliation={'catalogue_url':URL,'current_catalogue_detected':False if pending else None,
                                'source_lot_count':expected,'lots_discovered':0})
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(_inspect,targets))
        lots=[lot for lot,_ in results if lot];outcomes=[o for _,o in results]
        counts={key:sum(o['outcome']==key for o in outcomes) for key in ('detail_failure','past_auction','classification_rejected','commercial','mixed_use')}
        dates=sorted({_date(t[2].get('Auction','')) for t in targets}-{None})
        current=any(d>=date.today().isoformat() for d in dates)
        authoritative=complete and not counts['detail_failure'] and current
        status='LIVE' if authoritative else 'DEGRADED' if lots else 'FAILED'
        return SourceResult(SOURCE,status,lots,
            f'{len(targets)}/{expected if expected is not None else "unknown"} catalogue cards; {len(lots)} current commercial/mixed-use; '
            f'{counts["classification_rejected"]} residential exclusions; {counts["past_auction"]} past lots; {counts["detail_failure"]} detail failures',
            expected_count=len(lots) if authoritative else None,discovered_count=len(targets),
            authoritative_snapshot=authoritative,scope_dates=tuple(d for d in dates if d>=date.today().isoformat()),
            reconciliation={'catalogue_url':URL,'current_catalogue_detected':current,'source_lot_count':expected,
                'lots_discovered':len(targets),'lots_parsed':sum(o['parsed'] for o in outcomes),
                'commercial_candidates':counts['commercial'],'mixed_use_candidates':counts['mixed_use'],
                'commercial_mixed_candidates':len(lots),'classification_rejections':counts['classification_rejected'],
                'residential_exclusions':counts['classification_rejected'],'past_auction_exclusions':counts['past_auction'],
                'catalogue_complete':complete,'detail_failures':counts['detail_failure'],'lot_outcomes':outcomes})
    except Exception as exc:
        return SourceResult(SOURCE,'FAILED',[],str(exc),reconciliation={'catalogue_url':URL})
