"""Evidence-based social copy. No language-model calls or paid services."""
from datetime import datetime, timezone, timedelta, date
from hashlib import sha256
import json
import math
import re
from urllib.parse import urlencode
from collectors.financials import income_facts
from collectors.publication_quality import publication_exclusion, commercial_decision
from web_platform.catalogue import identity, slug
from web_platform.market_context import evidenced_rent, address_key
from web_platform.property_relationships import relationship

ORIGIN = 'https://auctiongeek.co.uk'
SELECTION = {'accessible_guide_ceiling': 250000,
             'expensive_guide_threshold': 500000, 'high_yield_percent': 10,
             'significant_guide_reduction_percent': 20}

def editorial_interest(row, archive=(), config=None):
    """Explain why a lot merits a post, independently of its eligibility checks."""
    policy = {**SELECTION, **((config or {}).get('editorial_selection') or {})}
    price = row.get('guide_price_upper') or row['guide_price']
    rent = evidenced_rent(row)
    yield_pct = 100 * rent / price if rent else 0
    reasons = []
    score = 0
    if price <= policy['accessible_guide_ceiling']:
        reasons.append('accessible guide price'); score += 16
    if yield_pct >= policy['high_yield_percent']:
        reasons.append('high gross yield at guide'); score += 10 + min(yield_pct, 15) / 3
    # An explicit description of the subject can correct a broad/mistaken type.
    # Never treat a nearby hotel, proposed hotel or sales adjective as the asset.
    text = row.get('description') or ''
    hotel = re.search(r'\bthe property comprises (?:a |an )?(?:(?:modern|purpose-built|refurbished) )?(?:[A-Z][\w-]* )?hotel\b', text, re.I)
    former_church = re.search(r'\b(?:acquire (?:this|the)|(?:this|the) property (?:is|comprises)) (?:a |an )?former (church|chapel)\b', text, re.I)
    unit_match = re.search(r'\b(?:comprising|comprises) (two|three|four|five|six|[2-9]) (?:commercial |retail |shop )?units\b', text, re.I)
    partial = re.search(r'\btwo are currently let and income producing,? while the remaining two are vacant\b', text, re.I)
    details = []
    if hotel: details.append('The property includes a hotel.')
    if former_church: details.append('The property is a former '+former_church[1].lower()+'.')
    if unit_match:
        details.append(f'The offering comprises {unit_match[1].lower()} commercial units.')
        reasons.append('multiple commercial units'); score += 6
    if partial:
        details.append('Two commercial units are let and two are vacant, offering scope to increase income through reletting.')
        reasons.append('existing lettings and vacant space'); score += 12
    distinctive = str(row.get('property_type') or '').strip().lower() in {
        'hotel', 'hotels', 'leisure', 'pub', 'public house', 'cinema', 'theatre',
        'church', 'chapel', 'petrol station', 'car park', 'marina', 'holiday park'} or bool(hotel or former_church)
    if distinctive:
        reasons.append('distinctive property type'); score += 12
    reductions = [h for h in history_context(row, archive) if h['price_comparable'] and
                  100 * (h['previous_guide'] - h['current_guide']) / h['previous_guide'] >= policy['significant_guide_reduction_percent']]
    if reductions:
        reasons.append('substantial same-interest guide reduction'); score += 10
    expensive = price > policy['expensive_guide_threshold']
    # A large price tag, named tenant or yield by itself is not a story.
    eligible = any(r != 'accessible guide price' for r in reasons) and (not expensive or distinctive or bool(reductions) or bool(partial))
    if eligible and clean_tenant(row): score += 2
    question = None
    if eligible and partial:
        question = 'Would you take on the vacant units, or prefer a fully let investment?'
    elif eligible and yield_pct >= policy['high_yield_percent']:
        question = 'At this guide price, what would you examine first: the lease terms or the building’s running costs?'
    elif eligible and price <= policy['accessible_guide_ceiling']:
        question = 'Would you consider a property at this guide price for your first commercial investment?'
    elif eligible and distinctive:
        question = 'Would this type of property interest you more than a conventional shop or office investment?'
    elif eligible and reductions:
        question = 'What would you want to understand before bidding at the lower guide price?'
    return {'eligible': eligible, 'score': score, 'reasons': reasons, 'question': question, 'details': details}
EDUCATION = [
    ('gross-yield', 'Gross yield is the starting point',
     'A property producing £20,000 in annual rent has a 10% gross yield at a £200,000 purchase price. At £250,000, the same rent produces 8%. These are illustrative figures.\n\nPurchase costs, repairs, insurance and empty periods reduce the return. Compare properties using the same assumptions before deciding what to bid.',
     [('£20,000', 'Illustrative annual rent'), ('£200,000 → £250,000', 'Illustrative purchase price'), ('10% → 8%', 'Gross yield before costs')]),
    ('lease-break', 'Read beyond the lease expiry date',
     'A tenant break clause may allow a tenant to leave before the lease expires. Check the earliest break date, the notice period and the conditions attached to it.\n\nWhen comparing investments, consider how long it could take to find another tenant and what costs would continue while the property is empty.',
     [('Break date', 'When could the tenant leave?'), ('Reletting costs', 'What would you need to fund?')]),
    ('property-history', 'A previous auction price needs context',
     'Before comparing two auction prices, check that both listings cover the same accommodation and legal interest. A whole freehold building and a lease of one shop are different investments.\n\nAlso distinguish a guide price from a reported sale result. A lower guide alone does not establish that a property is a bargain.',
     [('Same property?', 'Check accommodation and tenure'), ('Same price basis?', 'Guide prices and sale results differ')]),
]

def stamp(value):
    dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None: raise ValueError('Timestamp must include timezone')
    return dt

def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0

def cash(value):
    return f'£{value:,.0f}'

def fresh(value, now, hours):
    try: return -300 <= (now - stamp(value)).total_seconds() <= hours * 3600
    except (ValueError, TypeError): return False

def reject_reason(row, now, config, *, due=None):
    if identity(row) in config.get('excluded_property_ids', {}):
        return 'excluded from social promotion by owner'
    if str(row.get('status') or '').upper() not in {'CURRENT', 'AVAILABLE', 'FOR SALE'}:
        return 'not a current available lot'
    availability = str(row.get('source_availability') or '').upper()
    if availability and availability not in {'AVAILABLE', 'CURRENT', 'FOR SALE'}:
        return 'source no longer advertises availability'
    if not fresh(row.get('collected_at'), now, config['max_data_age_hours']): return 'stale property evidence'
    try: auction = date.fromisoformat(row.get('auction_date', ''))
    except (ValueError, TypeError): return 'auction date missing'
    lead = (auction - (due or now).date()).days
    if not config['minimum_auction_lead_days'] <= lead <= config['maximum_auction_lead_days']:
        return 'auction outside promotion window'
    if publication_exclusion(row) or commercial_decision(row) is not True: return 'commercial eligibility not established'
    if not row.get('url') or not re.match(r'^https?://', row['url']): return 'source link missing'
    if not row.get('address') or len(row['address']) > 180 or re.search(r'auction details|guide price|recently added', row['address'], re.I): return 'address unsuitable'
    if not positive(row.get('guide_price')): return 'guide missing'
    if row.get('guide_price_upper') is not None and (not positive(row['guide_price_upper']) or row['guide_price_upper'] < row['guide_price']):
        return 'inconsistent guide range'
    rent = evidenced_rent(row)
    if re.search(r'\b(?:not (?:currently )?paying rent|rent (?:is |remains )?unpaid|rent arrears)\b', row.get('description') or '', re.I):
        return 'rent payment issue requires editorial review'
    if row.get('annual_rent') and not rent: return 'current rent not established'
    if rent:
        # A number elsewhere on the listing is not evidence of current rent.
        parsed = income_facts(row.get('description') or '').get('annual_rent')
        schedules = row.get('tenancy_schedule') or []
        try: schedule_total = sum(float(x.get('Current Rent (PA)') or 0) for x in schedules)
        except (ValueError, TypeError): schedule_total = 0
        if schedule_total and abs(schedule_total-rent)>1: return 'tenancy schedule disagrees with total rent'
        if re.search(r'combined (?:gross )?annual income|two commercial units|\bHMO\b', row.get('description') or '', re.I) and schedule_total != rent:
            return 'multi-let income requires reconciled schedule'
        if parsed != rent and schedule_total != rent: return 'rent lacks matching source wording or schedule'
        if 100 * rent / row['guide_price'] > config['maximum_automatic_gross_yield']: return 'unusual yield needs editorial review'
    if re.search(r'\b(?:withdrawn|sold prior|sale agreed|postponed)\b', str(row.get('availability_note') or ''), re.I):
        return 'availability warning'
    return None

def clean_tenant(row):
    text = row.get('description') or ''
    # Only the tenant in a complete letting statement, never a neighbouring occupier.
    match = re.search(r'\bLet to ([^.;\n]{2,100}?)\s+on\s+(?:a |an |the )', text, re.I)
    if not match: return None
    value = re.split(r'\s+(?:at\s+£|currently trading as)',match[1],flags=re.I)[0].strip()
    if len(value) > 80 or re.search(r'\b(?:private|individual|various|tenants|vacant|agreed)\b', value, re.I): return None
    return value

def history_context(row, archive):
    result = []
    for old in archive:
        if address_key(old.get('address')) != address_key(row['address']): continue
        if not old.get('auction_date') or old['auction_date'] >= row['auction_date']: continue
        link = relationship(old, row, same_address=True)
        if not link or link['match_type'] != 'exact_match': continue
        result.append({'auction_date': old['auction_date'], 'source': old.get('source'), 'url': old.get('url'),
                       'kind': 'previous_appearance', 'price_comparable': False})
        # Price comparisons require explicit title/extent evidence, in addition
        # to the shared matching engine. Missing scope never means unchanged.
        same_scope = (old.get('title_numbers') and old.get('title_numbers') == row.get('title_numbers')
                      and old.get('unit_count') is not None and old.get('unit_count') == row.get('unit_count')
                      and positive(row.get('area_sqft')) and old.get('area_sqft') == row['area_sqft']
                      and old.get('tenure') == row.get('tenure')
                      and old.get('annual_rent') == row.get('annual_rent'))
        ceiling = row.get('guide_price_upper') or row['guide_price']
        if link['price_comparable'] and same_scope and positive(old.get('guide_price')) and old['guide_price'] > ceiling:
            result[-1].update(price_comparable=True, previous_guide=old['guide_price'], current_guide=ceiling)
    return sorted(result, key=lambda x: x['auction_date'], reverse=True)

def property_post(row, service, archive=(), config=None):
    key = identity(row)
    price = row['guide_price']; upper = row.get('guide_price_upper')
    guide = cash(price) + ('–' + cash(upper) if upper and upper != price else '')
    guide_suffix = '+' if '+' in (row.get('guide_price_text') or '') and not upper else ''
    guide += guide_suffix
    when = date.fromisoformat(row['auction_date']).strftime('%-d %B %Y')
    rent = evidenced_rent(row)
    lines = [row['address'], f'{row["source"]} · {when} · Guide {guide}']
    stats = [(guide, 'Auction guide price')]
    if rent:
        y = 100 * rent / (upper or price)
        basis = 'the upper guide price' if upper and upper != price else 'the guide price'
        lines.append(f'The advertised annual rent of {cash(rent)} produces a {y:.2f}% gross yield at {basis}, before purchase and running costs.')
        stats.append((cash(rent), 'Advertised annual rent'))
        stats.append((f'{y:.2f}%', 'Gross yield at '+('upper guide' if upper and upper != price else 'guide')))
    tenant = clean_tenant(row)
    if tenant: lines.append(f'The property includes space let to {tenant}.')
    if row.get('tenure'): lines.append(f'Tenure: {row["tenure"]}.')
    history = history_context(row, archive)
    if history:
        old = history[0]
        if old['price_comparable']:
            lines.append(f'The current guide is {cash(old["current_guide"])} compared with {cash(old["previous_guide"])} at the previous auction. These are guide prices, not sale results.')
        lines.append(f'An earlier auction appearance is recorded with {old["source"]} on {date.fromisoformat(old["auction_date"]).strftime("%-d %B %Y")}.')
    interest = editorial_interest(row, archive, config)
    lines.extend(interest['details'])
    if interest['question']: lines.append(interest['question'])
    lines.append('Check the tenancy terms, buyer’s fees and legal pack when assessing your bid.')
    canonical = ORIGIN + f'/property/{key}/{slug(row["address"])[:110]}/'
    track = canonical + '?' + urlencode({'utm_source': service, 'utm_medium': 'organic_social', 'utm_campaign': 'auction_properties', 'utm_content': key})
    if service == 'facebook': lines.append('Explore the property and its free snapshot on Auction Geek:\n'+track)
    else:
        lines.append('Explore this property on Auction Geek via the website link in our profile. Search for '+row['address'].split(',')[0]+'.')
        lines.append('#AuctionGeek #CommercialProperty #PropertyAuctions')
    fingerprint_fields = ['address','auction_date','guide_price','guide_price_upper','annual_rent','tenure','description','status','source_availability']
    facts = {k: row.get(k) for k in fingerprint_fields}
    evidence = {'url': row['url'], 'observed_at': row['collected_at'], 'facts': {k:v for k,v in facts.items() if k!='description'}, 'history': history,
                'source_text_sha256':sha256(str(row.get('description') or '').encode()).hexdigest(),
                'calculation': f'{rent} / {upper or price} * 100' if rent else None}
    return {'key': service+':'+key, 'property_id': key, 'kind': 'property', 'service': service,
            'asset_key':address_key(row['address'])+'|'+str(row.get('tenure') or '').lower(),
            'address': row['address'], 'title': row['address'], 'subtitle': f'{row["source"]} · {when}',
            'stats': stats, 'caption': '\n\n'.join(lines), 'canonical_url': canonical, 'tracking_url': track,
            'auction_date': row['auction_date'], 'evidence': evidence, 'editorial_interest': interest,
            'fingerprint': sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest(),
            'image_source': row.get('image_url')}

def education_post(service, index=0):
    key, title, body, stats = EDUCATION[index % len(EDUCATION)]
    url = ORIGIN+'/?'+urlencode({'utm_source':service,'utm_medium':'organic_social','utm_campaign':'auction_research','utm_content':key})
    ending = 'Explore commercial auctions and free property snapshots on Auction Geek:\n'+url if service == 'facebook' else 'Explore commercial auctions and free property snapshots through the website link in our profile.\n\n#AuctionGeek #CommercialProperty #PropertyResearch'
    return {'key':service+':education:'+key,'kind':'education','service':service,'title':title,'subtitle':'PROPERTY RESEARCH',
            'stats':stats,'caption':title+'\n\n'+body+'\n\n'+ending,'canonical_url':ORIGIN+'/',
            'tracking_url':url,'evidence':{'basis':'Editorial explainer; hypothetical numbers explicitly labelled'},'fingerprint':sha256(body.encode()).hexdigest()}

def candidates(snapshot, now, config):
    if not fresh(snapshot.get('generated_at'), now, config['max_data_age_hours']): raise ValueError('Catalogue is stale; no property promotions prepared')
    good=[]; rejected={}
    health={h['source']:h for h in snapshot.get('source_health',[])}
    for row in snapshot['properties']:
        reason=reject_reason(row,now,config)
        h=health.get(row.get('source'),{})
        if h.get('status') not in {'LIVE','OK'}: reason=reason or 'source collection not healthy'
        if reason: rejected[reason]=rejected.get(reason,0)+1; continue
        interest=editorial_interest(row,snapshot.get('archive',[]),config)
        if not interest['eligible']:
            reason='no supported editorial reason for promotion'
            rejected[reason]=rejected.get(reason,0)+1
            continue
        good.append((interest['score'],row))
    return [r for _,r in sorted(good,key=lambda x:(-x[0],x[1]['address']))], rejected

def samples(snapshot, now, config):
    rows,rejected=candidates(snapshot,now,config)
    selected=[]; types=set()
    for row in rows:
        typ=row.get('property_type')
        if typ in types:continue
        selected.append(row);types.add(typ)
        if len(selected)==2:break
    if len(selected)<2:raise ValueError('Not enough evidenced properties for the sample set')
    posts=[]
    for service in config['channels']:
        posts.extend(property_post(r,service,snapshot.get('archive',[]),config) for r in selected)
        posts.append(education_post(service))
    return posts,rejected
