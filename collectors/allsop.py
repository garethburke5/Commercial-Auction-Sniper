import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, nearest_card, image_from_soup, legal_pack

SOURCE = "Allsop Commercial"
BASE = "https://www.allsop.co.uk"
LANDING_PAGES = (BASE + "/auctions/commercial-auctions/", BASE + "/auctions/residential-auctions/")
SEARCHES = (
    BASE + "/property-search?future_auctions=on&page={page}&sortOrder=Max+Price&view=list",
    BASE + "/property-search?available_only=true&lot_type=both&page={page}&view=list",
)
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.I)
MONTHS = {"jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06","jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
MONTH_NAMES = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06","july":"07","august":"08","september":"09","october":"10","november":"11","december":"12","jan":"01","feb":"02","mar":"03","apr":"04","jun":"06","jul":"07","aug":"08","sep":"09","sept":"09","oct":"10","nov":"11","dec":"12"}
TERMINAL = re.compile(r"\b(?:sold\s*prior|withdrawn(?:\s+prior)?|postponed)\b", re.I)


def _lot_no(text):
    m = re.search(r"\bLOT\s+(\d+[A-Z]?)\b", text or "", re.I)
    return f"Lot {m.group(1)}" if m else "Lot TBC"


def _month_date(text):
    m = re.search(r"\b(?:Commercial|Residential)\s*-?\s*LOT(?:\s+\d+[A-Z]?)?\s*-?\s*([A-Za-z]{3,9})\s+(20\d{2})\b", text or "", re.I)
    if not m: return None
    mm = MONTHS.get(m.group(1).lower()[:3])
    return f"{m.group(2)}-{mm}-01" if mm else None


def _header_auction_date(text):
    m = re.search(r"\b(?:Commercial|Residential)\s*-\s*(\d{1,2})(?:st|nd|rd|th)?(?:\s*&\s*\d{1,2}(?:st|nd|rd|th)?)?\s+([A-Za-z]{3,9})\s+(20\d{2})", text or "", re.I)
    if not m: return None
    mm = MONTHS.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{mm}-{int(m.group(1)):02d}" if mm else None


def _exact_auction_date(text, fallback=None):
    """Return the actual day this lot is offered.

    Allsop residential auctions often span two days. The generic header says, for
    example, `Residential - 16th & 17th Sept 2026`, while each lot states `This Lot
    will be offered on Thursday 17th September`. The lot-specific statement must
    outrank the multi-day header or day-two lots disappear from the live board a day
    early. A year omitted from the lot-specific sentence is inherited from the
    catalogue header/fallback.
    """
    raw_text = text or ""
    header = _header_auction_date(raw_text)
    m = re.search(
        r"(?:this\s+lot\s+will\s+be\s+)?offered\s+on(?:\s+[A-Za-z]+)?\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?",
        raw_text, re.I,
    )
    if not m:
        m = re.search(r"(?:auction(?:ed)?(?: on)?|auction date\.?)[^\d]{0,35}(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(20\d{2}))?", raw_text, re.I)
    if m:
        year = m.group(3) or (header[:4] if header else fallback[:4] if fallback else str(date.today().year))
        mm = MONTH_NAMES.get(m.group(2).lower())
        if mm: return f"{year}-{mm}-{int(m.group(1)):02d}"
    if header: return header
    return fallback


def _page_auction_dates(s, today=None):
    today=today or date.today(); found=set(); text=norm(s.get_text(" ",strip=True))
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(20\d{2})\b",text,re.I):
        mm=MONTH_NAMES.get(m.group(2).lower()) or MONTHS.get(m.group(2).lower()[:3])
        if not mm: continue
        try: d=date(int(m.group(3)),int(mm),int(m.group(1)))
        except ValueError: continue
        if d>=today: found.add(d.isoformat())
    return tuple(sorted(found))


def _date_for_card(card,page_dates):
    exact=_header_auction_date(card)
    if exact:return exact
    month=_month_date(card)
    if not month:return None
    matches=[d for d in page_dates if d[:7]==month[:7]]
    return matches[0] if len(matches)==1 else None


def _card_is_target(card):
    low=(card or "").lower()
    if "commercial lot" in low or "commercial - lot" in low:return True
    mixed=("mixed use","mixed-use","commercial & residential","commercial and residential","shop and residential","retail and residential","commercial unit")
    return any(x in low for x in mixed) and is_commercial(card)


def _auction_tile(card):
    return bool(re.search(r"\b(?:Commercial|Residential)\s*-?\s*LOT(?:\s+\d+[A-Z]?)?\s*-?\s*(?:[A-Za-z]{3,9}\s+20\d{2})?",card or "",re.I))


def _detail_is_target(text):
    low=" "+norm(text).lower()+" "
    if is_commercial(text):return True
    explicit=(" mixed use "," mixed-use "," commercial premises"," commercial unit"," commercial accommodation"," commercial floor"," use class e"," class e use"," retail unit"," retail premises"," ground floor retail"," shop and "," shop with "," office building"," office premises"," former office"," warehouse"," industrial"," public house"," restaurant"," business premises"," commercial garage"," lock up garage")
    return any(x in low for x in explicit)


def _allsop_image(s,base):
    bad=("logo","favicon","icon","sprite","placeholder","social","avatar","staff","team","profile","award","rics","ombudsman","map","floorplan","epc")
    candidates=[]
    def add(raw,bonus=0):
        if not raw:return
        u=urljoin(base,str(raw).replace("\\/","/").strip(' "\''));low=u.lower()
        if any(x in low for x in bad):return
        score=bonus+(4 if "allsop" in low else 0)+(5 if any(x in low for x in ("lot","property","auction","media","image","photo","upload")) else 0)+(2 if re.search(r"\.(?:jpe?g|webp)(?:\?|$)",low) else 0)
        if any(x in low for x in ("thumb","thumbnail","small","100x","150x")):score-=3
        candidates.append((score,u))
    for attrs in ({"property":"og:image"},{"name":"twitter:image"},{"property":"twitter:image"},{"itemprop":"image"}):
        t=s.find("meta",attrs=attrs)
        if t and t.get("content"):add(t.get("content"),14)
    for img in s.find_all("img"):
        alt=norm(img.get("alt") or "").lower()
        if any(x in alt for x in bad):continue
        bonus=10 if any(x in alt for x in ("property","lot","investment","building")) else 0
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","data-large","src"):add(img.get(attr),bonus)
        for attr in ("srcset","data-srcset"):
            raw=img.get(attr)
            if raw:
                for part in raw.split(","):add(part.strip().split(" ")[0],bonus)
    raw=str(s).replace("\\/","/")
    for u in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',raw,re.I):add(u,4)
    if candidates:
        best={}
        for score,u in candidates:best[u]=max(score,best.get(u,-999))
        winner=max(best.items(),key=lambda kv:(kv[1],len(kv[0])))
        if winner[1]>0:return winner[0]
    g=image_from_soup(s,base)
    return g if g and not any(x in g.lower() for x in bad) else None


def _bounded_card(anchor,max_chars=3200):
    node=anchor;best=norm(anchor.get_text(" ",strip=True))
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        links={urljoin(BASE,a.get("href") or "").split("?",1)[0] for a in node.find_all("a",href=True) if "/lot-overview/" in (a.get("href") or "")}
        if len(links)>1:break
        text=norm(node.get_text(" ",strip=True))
        if not text or len(text)>max_chars:break
        if len(text)>len(best):best=text
    return best


def _card_image(anchor):
    node=anchor
    for _ in range(6):
        node=getattr(node,"parent",None)
        if node is None:break
        links={urljoin(BASE,a.get("href") or "").split("?",1)[0] for a in node.find_all("a",href=True) if "/lot-overview/" in (a.get("href") or "")}
        if len(links)>1:break
        try:
            img=_allsop_image(node,BASE)
            if img:return img
        except Exception:pass
    return None


def _extract_targets(s,found,include_all_auction_lots=False):
    page_dates=_page_auction_dates(s)
    for a in s.find_all("a",href=True):
        href=urljoin(BASE,a.get("href") or "").split("?",1)[0]
        if "/lot-overview/" not in href:continue
        card=_bounded_card(a) or nearest_card(a,3200) or norm(a.get_text(" ",strip=True))
        target=_card_is_target(card)
        if not target and not (include_all_auction_lots and _auction_tile(card)):continue
        candidate={"card":card,"image":_card_image(a),"auction_date":_date_for_card(card,page_dates),"card_target":target}
        prev=found.get(href)
        if isinstance(prev,dict):
            for k in ("image","auction_date"):
                if not candidate.get(k):candidate[k]=prev.get(k)
            candidate["card_target"]=bool(candidate["card_target"] or prev.get("card_target"))
        found[href]=candidate


def _discover():
    found={}
    for url in LANDING_PAGES:
        try:_extract_targets(soup(url,use_browser=False),found)
        except Exception:
            try:_extract_targets(soup(url,use_browser=True),found)
            except Exception:pass
    for template in SEARCHES:
        repeated=None
        for page in range(1,31):
            try:s=soup(template.format(page=page),use_browser=False)
            except Exception:continue
            local={};_extract_targets(s,local,include_all_auction_lots=True)
            for href,meta in local.items():
                prev=found.get(href)
                if isinstance(prev,dict):
                    if not meta.get("image"):meta["image"]=prev.get("image")
                    if not meta.get("auction_date"):meta["auction_date"]=prev.get("auction_date")
                    meta["card_target"]=bool(meta.get("card_target") or prev.get("card_target"))
                found[href]=meta
            sig=tuple(sorted(local))
            if page>1 and (not sig or sig==repeated):break
            repeated=sig
    return found


def _candidate_is_current_or_future(card,today=None,exact_date=None):
    today=today or date.today()
    if exact_date:
        try:return date.fromisoformat(exact_date[:10])>=today
        except Exception:pass
    raw=_header_auction_date(card) or _month_date(card)
    if not raw:return True
    try:y,m,_=(int(x) for x in raw.split("-",2))
    except Exception:return True
    return (y,m)>=(today.year,today.month)


def _live_status_probe(s,card=""):
    # Never search footer/related-lot chrome for lifecycle state.
    main=s.find("main") or s; bits=[]
    for tag in main.find_all(["h1","h2","h3","p","strong"],limit=18):
        t=norm(tag.get_text(" ",strip=True))
        if t:bits.append(t)
        if len(" ".join(bits))>1800:break
    return " ".join(bits)


def _main_identity(s):
    main=s.find("main") or s
    strings=[norm(x) for x in main.stripped_strings]
    lot="Lot TBC";address=None
    for i,t in enumerate(strings[:120]):
        m=re.fullmatch(r"LOT\s+(\d+[A-Z]?)\s*-\s*.+",t,re.I)
        if not m:continue
        lot=f"Lot {m.group(1)}"
        for candidate in strings[i+1:i+12]:
            if POSTCODE.search(candidate) and 8<=len(candidate)<=240:
                address=candidate;break
        break
    if not address:
        for t in strings[:100]:
            if POSTCODE.search(t) and 8<=len(t)<=240 and not re.search(r"guide price|register to bid|looking for finance",t,re.I):
                address=t;break
    return lot,address,main


def _address_from_soup(s,card=""):
    _lot,address,_main=_main_identity(s)
    return address


def _teaser_address(card):
    text=norm(card);m=re.search(r"FEATURED LOT\s+(.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b)",text,re.I)
    if m:return norm(m.group(1))
    m=re.search(r"\b([A-Z][A-Za-z .'-]{2,60}\s+[A-Z]{1,2}\d[A-Z\d]?)\b",text)
    return norm(m.group(1)) if m else None


def _teaser_title(card):
    m=re.search(r"FEATURED LOT\s+.{2,100}?\b[A-Z]{1,2}\d[A-Z\d]?\b\s+(.+?)(?:Guide Price|Yield|£|$)",norm(card),re.I)
    return norm(m.group(1)) if m else None


def _teaser_lot(url,card,image_url=None,auction_date=None):
    if not _card_is_target(card):return None
    address=_teaser_address(card)
    if not address:return None
    title=_teaser_title(card)
    return Lot(source=SOURCE,url=url,address=address,lot_number=_lot_no(card),auction_date=auction_date or _month_date(card),guide_price=parse_guide(card),image_url=image_url,property_type=title[:180] if title else "Commercial / mixed-use auction lot",description=card[:3500],status="CURRENT").finalise()


def _hydrate(item,today=None):
    today=today or date.today();url,meta=item
    card=meta.get("card") or ""; teaser_image=meta.get("image"); teaser_date=meta.get("auction_date"); card_target=bool(meta.get("card_target"))
    try:s=soup(url,use_browser=False)
    except Exception:
        try:s=soup(url,use_browser=True)
        except Exception:return _teaser_lot(url,card,teaser_image,teaser_date) if card_target else None
    lot_number,address,main=_main_identity(s)
    text=norm(main.get_text(" ",strip=True)); auction_date=_exact_auction_date(text,teaser_date)
    # Exact page date is authoritative. Search results routinely expose historic
    # lots alongside future stock; never let a contaminated card make them live.
    if auction_date:
        try:
            if date.fromisoformat(auction_date[:10])<today:return None
        except Exception:pass
    lifecycle=_live_status_probe(s)
    terminal=None
    if re.search(r"sold\s*prior",lifecycle,re.I):terminal="SOLD PRIOR"
    elif re.search(r"withdrawn",lifecycle,re.I):terminal="WITHDRAWN"
    elif re.search(r"postponed",lifecycle,re.I):terminal="POSTPONED"
    if not address:return _teaser_lot(url,card,teaser_image,auction_date) if card_target and not terminal else None
    title_tag=main.find("h1") or s.find("h1"); opportunity=norm(title_tag.get_text(" ",strip=True)) if title_tag else ""
    combined=norm(opportunity+" "+text)
    if not _detail_is_target(combined):return None
    image=_allsop_image(main,url) or teaser_image
    lp_url,lp_status=legal_pack(s,url);rent=parse_rent(combined);guide=parse_guide(combined);tenure=parse_tenure(combined)
    has_vacant=bool(re.search(r"\bvacant\b|vacant possession",combined,re.I));occupation="Part vacant / part let" if has_vacant and rent else "Vacant / vacant possession" if has_vacant else "Tenanted" if rent else None
    return Lot(source=SOURCE,url=url,address=address,lot_number=lot_number,auction_date=auction_date,image_url=image,guide_price=guide,annual_rent=rent,tenure=tenure,vat_status=parse_vat(combined),legal_pack_status=lp_status,legal_pack_url=lp_url,description=combined[:6500],occupation=occupation,property_type=opportunity[:180] if opportunity else None,status=terminal or "CURRENT",development_potential=True if re.search(r"development|redevelopment|planning potential",combined,re.I) else None,asset_management=True if re.search(r"asset management|part vacant|reversion|reconfigure",combined,re.I) else None,residential_conversion=True if re.search(r"conversion to residential|residential conversion",combined,re.I) else None,fri=True if re.search(r"\bFRI\b|full repairing and insuring",combined,re.I) else None).finalise()


def collect():
    try:
        targets=_discover()
        if not targets:return SourceResult(SOURCE,"CATALOGUE PENDING",[],"Allsop canonical auction pages and public search endpoints returned no auction lot pages.",discovered_count=0)
        live_targets={u:m for u,m in targets.items() if _candidate_is_current_or_future(m.get("card") or "",exact_date=m.get("auction_date"))}
        lots=[];failures=0
        with ThreadPoolExecutor(max_workers=14) as ex:
            futs={ex.submit(_hydrate,item):item[0] for item in live_targets.items()}
            for f in as_completed(futs):
                try:
                    lot=f.result()
                    if lot:lots.append(lot)
                except Exception:failures+=1
        lots=list({x.url:x for x in lots}.values());available=[x for x in lots if x.status=="CURRENT"];terminal=[x for x in lots if x.status!="CURRENT"]
        status="LIVE" if lots and failures==0 else "DEGRADED" if lots else "FAILED" if failures else "CATALOGUE PENDING"
        msg=f"Allsop exact-page current/future sweep: {len(live_targets)} candidate pages hydrated; {len(available)} available commercial/mixed-use lots; {len(terminal)} unavailable history rows retained; {failures} detail failures. Exact lot page controls identity/date/status."
        return SourceResult(SOURCE,status,lots,msg,discovered_count=len(live_targets),authoritative_snapshot=bool(status=="LIVE" and not failures),scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})))
    except Exception as exc:return SourceResult(SOURCE,"FAILED",[],f"Allsop collection failed: {exc}")