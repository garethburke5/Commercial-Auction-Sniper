from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import quote_plus

import requests

INDEX_URL = 'https://raw.githubusercontent.com/garethburke5/mega-cap-dip-radar/auction-history-runner/auction_history_output/history_v2/allsop_index.json'
EVENTS_URL = 'https://raw.githubusercontent.com/garethburke5/mega-cap-dip-radar/auction-history-runner/auction_history_output/history_v2/allsop_events.json'
POSTCODE_RE = re.compile(r'\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b', re.I)
UNIT_WORDS = {'unit','units','flat','flats','suite','shop','shops','floor','floors','ground','first','second','third'}
NOISE = {'the','and','at','of','property','premises','freehold','leasehold','road','rd','street','st','avenue','ave','lane','ln','drive','dr'}


def _text(v):
    return re.sub(r'\s+', ' ', str(v or '')).strip()


def postcode(address):
    m = POSTCODE_RE.search(_text(address).upper())
    return re.sub(r'\s+', '', m.group(1).upper()) if m else None


def normalize_address(address):
    s = _text(address).lower().replace('&', ' and ')
    s = POSTCODE_RE.sub(' ', s)
    for a,b in {'street':'st','road':'rd','avenue':'ave','lane':'ln','drive':'dr'}.items():
        s = re.sub(rf'\b{a}\b', f' {b} ', s)
    return _text(re.sub(r'[^a-z0-9]+', ' ', s))


def building_tokens(address):
    return set(re.findall(r'\b\d+[a-z]?\b', normalize_address(address))[:6])


def street_tokens(address):
    out=[]
    for token in normalize_address(address).split():
        if token in NOISE or token in UNIT_WORDS or re.fullmatch(r'\d+[a-z]?', token):
            continue
        out.append(token)
    return out


def match_score(current_address, historical_address):
    a,b=_text(current_address),_text(historical_address)
    if not a or not b:
        return 0.0,'NONE'
    pa,pb=postcode(a),postcode(b)
    if pa and pb and pa != pb:
        return 0.0,'NONE'
    score=0.55 if pa and pb and pa == pb else (0.05 if pa or pb else 0.0)
    ba,bb=building_tokens(a),building_tokens(b)
    if ba and bb:
        overlap=len(ba & bb)/max(1,min(len(ba),len(bb)))
        if overlap == 0 and pa and pb:
            return min(score,0.55),'POSSIBLE_RELATED'
        score += 0.25*overlap
    sa,sb=' '.join(street_tokens(a)),' '.join(street_tokens(b))
    if sa and sb:
        score += 0.20*SequenceMatcher(None,sa,sb).ratio()
    score=min(score,1.0)
    level='EXACT' if score >= 0.94 else ('HIGH' if score >= 0.82 else ('PROBABLE' if score >= 0.72 else ('POSSIBLE_RELATED' if score >= 0.55 else 'NONE')))
    return round(score,4),level


def _get_json(url, timeout=12):
    r=requests.get(url,timeout=timeout,headers={'User-Agent':'AuctionSniper-HistoryV2/1.0'})
    r.raise_for_status()
    return r.json()


@lru_cache(maxsize=1)
def load_index():
    return _get_json(INDEX_URL)


@lru_cache(maxsize=1)
def load_events():
    payload=_get_json(EVENTS_URL,timeout=25)
    return payload, {e.get('event_id'):e for e in payload.get('events',[]) if e.get('event_id')}


def find_history(address, include_possible=False, limit=20):
    pc=postcode(address)
    if not pc:
        return []
    try:
        idx=load_index()
    except Exception:
        return []
    candidates=(idx.get('by_postcode') or {}).get(pc) or []
    matches=[]
    for row in candidates:
        score,level=match_score(address,row.get('address'))
        if level in ('EXACT','HIGH','PROBABLE') or (include_possible and level=='POSSIBLE_RELATED'):
            matches.append({**row,'match_score':score,'match_level':level})
    matches.sort(key=lambda x:(x['match_score'],x.get('auction_date') or ''),reverse=True)
    return matches[:limit]


def history_action(address):
    matches=find_history(address)
    if matches:
        url='/History?address='+quote_plus(_text(address))
        return {'internal':True,'count':len(matches),'url':url,'label':f'Previous auctions / sale history ({len(matches)})'}
    q=quote_plus(f'"{_text(address)}" (auction OR sold OR sale OR guide OR lot)')
    return {'internal':False,'count':0,'url':f'https://www.google.com/search?q={q}','label':'Previous auctions / sale history'}


def _money(v):
    try:
        return f'£{float(v):,.0f}'
    except Exception:
        return '—'


def history_panel_html(address):
    matches=find_history(address,include_possible=True,limit=50)
    if not matches:
        q=quote_plus(f'"{_text(address)}" (auction OR sold OR sale OR guide OR lot)')
        return (
            '<div class="historyV2"><h3>Previous auctions / sale history</h3>'
            '<p>No internal auction-history match yet.</p>'
            f'<p><a target="_blank" rel="noopener noreferrer" href="https://www.google.com/search?q={q}">Search web for more history ↗</a></p></div>'
        )
    try:
        _payload,events=load_events()
    except Exception:
        events={}
    rows=[]
    seen=set()
    for m in matches:
        eid=m.get('event_id')
        if not eid or eid in seen:
            continue
        seen.add(eid)
        e=events.get(eid) or m
        evidence=e.get('evidence') or {}
        links=[]
        for key,label in [('listing_url','View lot evidence'),('results_url','Results page'),('auction_url','Auction page'),('legal_pack_url','Legal pack')]:
            url=_text(evidence.get(key))
            if url and all(url != x[0] for x in links):
                links.append((url,label))
        evidence_html=' · '.join(f'<a target="_blank" rel="noopener noreferrer" href="{html.escape(u,quote=True)}">{html.escape(label)} ↗</a>' for u,label in links) or 'Evidence link unavailable'
        sale=e.get('sale_price')
        guide=e.get('guide_price') if e.get('guide_price') is not None else e.get('guide_price_lower')
        rows.append(
            '<div class="historyEvent">'
            f'<div><b>{html.escape(_text(e.get("source")) or "Auction")}</b> · {html.escape(_text(e.get("auction_date")) or _text(e.get("auction_month")) or "Date unknown")} · Lot {html.escape(_text(e.get("lot_number")) or "—")}</div>'
            f'<div>{html.escape(_text(e.get("address_as_published")) or _text(m.get("address")))}</div>'
            f'<div>Guide <b>{_money(guide)}</b> · Sale/result <b>{_money(sale) if sale is not None else html.escape(_text(e.get("status")) or "—")}</b> · Rent <b>{_money(e.get("annual_rent"))}</b> · Yield <b>{html.escape(_text(e.get("gross_yield")) or "—")}</b></div>'
            f'<div>Tenure <b>{html.escape(_text(e.get("tenure")) or "—")}</b> · Match <b>{html.escape(m.get("match_level") or "")}</b> ({m.get("match_score",0):.0%})</div>'
            f'<div class="historyEvidence">{evidence_html}</div>'
            '</div>'
        )
    q=quote_plus(f'"{_text(address)}" (auction OR sold OR sale OR guide OR lot)')
    return (
        '<div class="historyV2"><h3>Previous auctions / sale history</h3>'
        f'<p><b>{html.escape(_text(address))}</b> · {len(rows)} internal match(es)</p>'
        +''.join(rows)+
        f'<p><a target="_blank" rel="noopener noreferrer" href="https://www.google.com/search?q={q}">Search web for more history ↗</a></p></div>'
    )
