import re
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .core import SourceResult, Lot, is_commercial, norm, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import nearest_card, legal_pack, enrich_common_fields
from .paul_fosh import _particulars, _primary_image
from .publication_quality import commercial_decision, MIXED
from .browser import get_html

SOURCE = "McHugh & Co"
BASE = "https://www.mchughandco.com"
URL = BASE + "/current-auction"
LANDING_URLS = (URL, BASE + "/pages/auctions", BASE + "/")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _fetch(url):
    last = None
    session = requests.Session()
    for attempt in range(3):
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if len(r.text) > 1000:
                return BeautifulSoup(r.text, "lxml")
        except Exception as exc:
            last = exc
            time.sleep(0.8 + attempt)
    try:
        return BeautifulSoup(get_html(url, use_browser=False), "lxml")
    except Exception as exc:
        raise exc from last


def _catalogue_soup():
    errors=[]; seen=set(); queue=list(LANDING_URLS)
    while queue:
        url=queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try: s=_fetch(url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}"); continue
        if any("/lot/details/" in (a.get("href") or "").lower() for a in s.find_all("a",href=True)):
            return s,url
        for a in s.find_all("a",href=True):
            href=urljoin(BASE,a.get("href") or "").split("?",1)[0]
            if urlparse(href).hostname == urlparse(BASE).hostname and ("/future-auctions/" in href or href.rstrip("/").endswith("/current-auction")) and href not in seen and href not in queue:
                queue.insert(0,href)
    raise RuntimeError("; ".join(errors) or "no McHugh current catalogue could be resolved")


def _auction_date(card):
    m=re.search(r"(?:End Time\s*-\s*|Auction Ended\s*-\s*)?(\d{1,2})/(\d{1,2})/(20\d{2})",card or "")
    if m: return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def _terminal_status(text):
    """Read explicit per-lot result labels only.

    Every McHugh bidding page contains generic help text headed 'Withdrawn,
    Postponed and Sold Prior Lots'. Bare phrase matching would therefore mark every
    live lot terminal. The catalogue uses explicit 'Result Sold Prior/Withdrawn'
    labels for actual lot lifecycle changes, so require that evidence.
    """
    probe=norm(text)
    if re.search(r"\bResult\s*:?\s*Sold\s+Prior\b",probe,re.I): return "SOLD PRIOR"
    if re.search(r"\bResult\s*:?\s*Withdrawn(?:\s+Prior)?\b",probe,re.I): return "WITHDRAWN"
    if re.search(r"\bResult\s*:?\s*Postponed\b",probe,re.I): return "POSTPONED"
    if re.search(r"\bResult\s*:?\s*Sold(?:\s+for|\s+at|$)",probe,re.I): return "SOLD"
    return None


def _targets(s):
    targets={}
    for a in s.find_all('a',href=True):
        href=urljoin(BASE,a['href']).split('?',1)[0].split('#',1)[0]
        if urlparse(href).hostname != urlparse(BASE).hostname or '/lot/details/' not in href.lower():continue
        card=a.find_parent(class_='grid-panel')
        seed=norm(card.get_text(' ',strip=True)) if card else nearest_card(a,3200)
        targets[href]=seed
    return targets


def _hydrate(href,card):
    auction_date=_auction_date(card)
    if not auction_date:raise ValueError('Lot has no evidenced auction closing date; no fixed-date fallback')
    if auction_date < date.today().isoformat():return None, 'past_sale'
    s=_fetch(href);h1=s.find('h1');text=_particulars(s)
    if not h1 or not text:raise ValueError('Exact lot address/particulars missing')
    address=norm(h1.get_text(' ',strip=True))
    mixed=bool(MIXED.search(card) or MIXED.search(text))
    card_residential=bool(re.search(r'\b(?:flat|maisonette|bungalow|(?:detached|terraced|terrace|vacant|freehold) house)\b',card,re.I))
    card_commercial=bool(re.search(r'\b(?:mixed[ -]use|retail|shop|office|industrial|warehouse|public house|restaurant|commercial)\b',card,re.I))
    decision=commercial_decision({'address':address,'description':text})
    if decision is False or (card_residential and not card_commercial and not mixed) or (decision is not True and not card_commercial):
        return None,'classification_rejected'
    lm=re.search(r'\bLot\s+(\d+[A-Z]?)\b',card,re.I)
    lp,lp_status=legal_pack(s,href)
    lot=Lot(source=SOURCE,url=href,address=address,lot_number='Lot '+lm.group(1).upper() if lm else None,
        auction_date=auction_date,image_url=_primary_image(s,href),image_is_primary=True,image_source_url=href,
        guide_price=parse_guide(card),annual_rent=parse_rent(text),tenure=parse_tenure(card+' '+text),
        vat_status=parse_vat(text),legal_pack_url=lp,legal_pack_status=lp_status,
        description=text,property_type='Mixed Use' if mixed else 'Commercial',
        status=_terminal_status(card) or 'CURRENT')
    return enrich_common_fields(lot,text).finalise(),'mixed_use' if mixed else 'commercial'


def collect():
    try:
        s,catalogue_url=_catalogue_soup();targets=_targets(s)
        lots=[];outcomes=[]
        def inspect(pair):
            href,card=pair
            try:
                lot,outcome=_hydrate(href,card)
                return lot,{'url':href,'outcome':outcome,'parsed':True}
            except Exception as exc:
                return None,{'url':href,'outcome':'detail_failure','parsed':False,'reason':f'{type(exc).__name__}: {exc}'}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for lot,outcome in pool.map(inspect,targets.items()):
                outcomes.append(outcome)
                if lot:lots.append(lot)
        failures=sum(x['outcome']=='detail_failure' for x in outcomes)
        excluded=sum(x['outcome']=='classification_rejected' for x in outcomes)
        past=sum(x['outcome']=='past_sale' for x in outcomes)
        scopes=tuple(sorted({d for card in targets.values() if (d:=_auction_date(card)) and d>=date.today().isoformat()}))
        complete=bool(targets and not failures and not past)
        status='LIVE' if complete else ('DEGRADED' if lots else 'FAILED')
        return SourceResult(SOURCE,status,lots,
            f'Current McHugh catalogue via {catalogue_url}: {len(targets)} lot pages discovered; '
            f'{len(targets)-failures-past} inspected; {len(lots)} commercial/mixed-use; {excluded} classification exclusions; '
            f'{failures} detail failures; {past} past-sale lots excluded.',
            expected_count=len(lots) if complete else None,discovered_count=len(targets),
            scope_dates=scopes,authoritative_snapshot=complete,reconciliation={
                'current_catalogue_detected':bool(scopes),'catalogue_url':catalogue_url,'source_lot_count':len(targets),
                'lots_discovered':len(targets),'lots_parsed':len(targets)-failures-past,
                'commercial_candidates':sum(x['outcome']=='commercial' for x in outcomes),
                'mixed_use_candidates':sum(x['outcome']=='mixed_use' for x in outcomes),
                'commercial_mixed_candidates':len(lots),'classification_rejections':excluded,
                'detail_failures':failures,'past_sale_exclusions':past,'lot_outcomes':outcomes})
    except Exception as exc:
        return SourceResult(SOURCE,'FAILED',[],f'McHugh catalogue failed after first-party route and transport fallbacks: {exc}')
