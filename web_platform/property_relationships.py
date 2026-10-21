"""Evidence-based links between offerings; never merge assets or access grants.

Numbered street components and explicit title identifiers are candidate anchors,
not proof that two lots comprise the same accommodation or legal interest.
"""
import re
from functools import lru_cache

PC = re.compile(r'\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b', re.I)
NUMBER = r'\d+[a-z]?(?:\s*[-/]\s*\d+[a-z]?)?'
UNIT = re.compile(r'^(?:(?:units?|flats?|apartments?|suites?|shops?)\s+[a-z0-9/-]+|(?:ground|first|second|third|upper|lower|basement)\s*(?:floor)?)(?:\s*,\s*|\s+(?:at|of)\s+)', re.I)

def norm(value):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 /-]', ' ', str(value or '').lower().replace('–','-').replace('—','-').replace('&',' and '))).strip()

@lru_cache(maxsize=32768)
def address_parts(address):
    codes=PC.findall(address or '')
    if len(codes)!=1:return ()
    pc=''.join(codes[0]).upper()
    text=PC.sub('',address).strip(' ,')
    # Retain unit qualifiers separately in the full address; remove only for
    # building candidate discovery. Do not use fuzzy street/name similarity.
    text=UNIT.sub('',text)
    parts=[]
    for component in re.split(r',|\s+(?:and|&)\s+(?=\d)',text,flags=re.I):
        m=re.fullmatch(r'\s*('+NUMBER+r')\s+([A-Za-z][A-Za-z .\x27-]*)\s*',component)
        if not m:continue
        number=re.sub(r'\s+','',m[1].lower())
        street=norm(m[2]);street=re.sub(r'\b(rd|st|ave)$',lambda m:{'rd':'road','st':'street','ave':'avenue'}[m[1]],street)
        # Large portfolios/ranges are not expanded into speculative links.
        bounds=re.fullmatch(r'(\d+)-(\d+)',number)
        if bounds and 0<int(bounds[2])-int(bounds[1])<=40:
            # Boundaries are explicit; interior numbers may refer to premises
            # on the opposite side of a street, so do not infer them.
            numbers=(bounds[1],bounds[2])
        else:numbers=(number,)
        parts.extend((pc,street,n) for n in numbers)
    return tuple(sorted(set(parts)))

def address_scope(address):
    """Keep building/unit prefixes and the numbered street; ignore locality only.

    Returns no signature for comma-less or compound addresses we cannot parse
    confidently. Such records can be related candidates, never exact matches.
    """
    text=PC.sub('',str(address or ''))
    if ',' not in text:return None
    components=[norm(c) for c in text.split(',') if norm(c)]
    scope=[];street_found=False
    for component in components:
        if re.match(r'^'+NUMBER+r'\s+[a-z]',component):
            # Do not consume locality appended to unstructured compound streets.
            if re.search(r'\band\b',component):return None
            component=re.sub(r'\b(rd|st|ave)$',lambda m:{'rd':'road','st':'street','ave':'avenue'}[m[1]],component)
            component=re.sub(r'\s*([-\/])\s*',r'\1',component)
            scope.append(component);street_found=True
        elif not street_found:scope.append(component)
        elif re.search(r'\b(?:units?|flats?|floors?|ground|basement|upper|lower|rear|land|garages?|parking|roof|airspace|rights|shops?|parts?)\b|\d',component):scope.append(component)
        else:break
    return tuple(scope) if street_found else None

def tenure_kind(row):
    text=norm(row.get('tenure'))
    if 'freehold' in text and 'leasehold' in text:return text
    if 'leasehold' in text:return 'leasehold'
    if 'freehold' in text:return 'freehold'
    return text or None

def titles(row):
    values=row.get('title_numbers') or row.get('title_number') or []
    if isinstance(values,str):values=re.split(r'[,;\s]+',values)
    return frozenset(str(v).upper() for v in values if re.fullmatch(r'[A-Za-z]{1,3}\d{2,}',str(v)))

def candidate_keys(row):
    keys=[('address',)+p for p in address_parts(str(row.get('address') or ''))]
    code=PC.search(str(row.get('postcode') or row.get('address') or ''))
    if code:keys.extend(('title',''.join(code.groups()).upper(),t) for t in titles(row))
    return keys

def relationship(previous,current,*,same_address=False):
    """Return a link classification and factual differences, or no relationship."""
    shared=set(candidate_keys(previous)) & set(candidate_keys(current))
    if not same_address and not shared:return None
    ps,cs=address_scope(previous.get('address')),address_scope(current.get('address'))
    same_address=same_address or bool(ps and ps==cs)
    before,after=tenure_kind(previous),tenure_kind(current)
    reasons=[]
    if before and after and before!=after:
        reasons.append('The earlier offering was '+before+'. This listing offers a '+after+' interest.')
    if not same_address:
        old_parts=set(address_parts(str(previous.get('address') or '')));new_parts=set(address_parts(str(current.get('address') or '')))
        extra_roads={p[1] for p in old_parts}-{p[1] for p in new_parts}
        if new_parts and new_parts < old_parts and extra_roads:
            extras=sorted({p[2]+' '+p[1].title() for p in old_parts if p[1] in extra_roads})
            reasons.append('The earlier offering also included '+', '.join(extras)+'.')
        elif ps and cs:
            reasons.append('Both records identify the same building or site, but use different unit or address descriptions.')
        else:
            reasons.append('The records share a building address or title, but the accommodation covered by each offering needs to be checked.')
    for field,label in [('unit_count','number of units'),('commercial_units','number of commercial units')]:
        if previous.get(field) is not None and current.get(field) is not None and previous[field]!=current[field]:
            reasons.append('The recorded '+label+' differs between the offerings.')
    def schedule_addresses(r):
        return frozenset(norm(u.get('Address') or u.get('address')) for u in r.get('tenancy_schedule') or [] if isinstance(u,dict) and (u.get('Address') or u.get('address')))
    pu,cu=schedule_addresses(previous),schedule_addresses(current)
    if pu and cu and pu!=cu:
        reasons.append('The tenancy schedules list different units.')
    def lease_years(r):
        text=str(r.get('tenure') or '')+' '+str(r.get('description') or '')
        m=re.search(r'(?:new\s+)?(\d{2,4})[ -]+year\s+lease(?:hold)?\b',text,re.I)
        return int(m[1]) if m else None
    py,cy=lease_years(previous),lease_years(current)
    if before==after=='leasehold' and py and cy and py!=cy and re.search(r'new\s+\d{2,4}[ -]+year\s+lease',str(current.get('tenure') or '')+' '+str(current.get('description') or ''),re.I):
        reasons.append('The advertised leasehold terms differ: '+str(py)+' years previously and '+str(cy)+' years in this offering.')
    pt,ct=titles(previous),titles(current)
    if pt and ct and pt!=ct:reasons.append('The recorded title numbers differ between the offerings.')
    # Compare structured floor areas only; absence is not a zero or evidence of change.
    def area(r):
        value=r.get('area_sqft')
        if isinstance(value,(int,float)):return value
        m=re.search(r'([\d,.]+)\s*(?:sq\s*ft|sqft|ft²)',str(r.get('floor_area') or ''),re.I)
        return float(m[1].replace(',','')) if m else None
    a,b=area(previous),area(current)
    if not reasons and all(isinstance(v,(int,float)) and not isinstance(v,bool) and v>0 for v in (a,b)) and abs(a-b)/max(a,b)>.05:
        reasons.append('The recorded floor area differs from this listing; the accommodation may have changed.')
    if reasons:
        return {'match_type':'related_interest','price_comparable':False,'relationship_reasons':reasons,
                'current_lease_years':cy,'current_lease_is_new':bool(cy and re.search(r'new\s+'+str(cy)+r'[ -]+year\s+lease',str(current.get('tenure') or '')+' '+str(current.get('description') or ''),re.I)),
                'interest_changed':bool(before and after and before!=after),
                'match_basis':'Shared published building address or title; a different property interest or extent is recorded.'}
    if same_address:
        return {'match_type':'exact_match','price_comparable':bool(before and after and before==after),
                'relationship_reasons':[], 'match_basis':'Matching address and recorded interest' if before and after else 'Matching address; legal interest not fully recorded'}
    return None

def result_evidence(row):
    """A source's sold status is a reported result, never proof of completion."""
    status=re.sub(r'[\s-]+','_',str(row.get('source_availability') or row.get('status') or '').lower())
    if status in {'unsold','not_sold','available','available_at'}:
        return {'label':'Unsold' if status in {'unsold','not_sold'} else 'Available — no sale recorded','sale_price':None,'kind':'unsold' if status in {'unsold','not_sold'} else 'unverified'}
    if status in {'withdrawn','withdrawn_prior','postponed'}:
        return {'label':status.replace('_',' ').capitalize(),'sale_price':None,'kind':status}
    if status in {'sold','sold_prior','sold_after','sold_post','sold_at_auction'}:
        suffix={'sold_prior':' before auction','sold_after':' after auction','sold_post':' after auction'}.get(status,'')
        return {'label':'Reported sold'+suffix,'sale_price':row.get('sale_price'),'kind':'reported_sale'}
    return {'label':'Outcome not verified','sale_price':None,'kind':'unverified'}
