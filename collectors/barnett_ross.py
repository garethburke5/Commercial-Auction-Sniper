import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

from .core import Lot, SourceResult, norm, parse_guide, parse_rent, parse_tenure, parse_vat, is_commercial
from .utils import soup, image_from_soup, legal_pack

SOURCE = "Barnett Ross"
BASE = "https://www.barnettross.co.uk"
CURRENT = BASE + "/current.php"


def _parse_date(text):
    m = re.search(r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(20\d{2})", text or "", re.I)
    if not m: return None
    try: return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date().isoformat()
    except ValueError: return None


def _discover(s):
    links = {}; detail_re = re.compile(r"(?:/)?property\.php\?id=\d+", re.I)
    for a in s.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "")
        if detail_re.search(href): links[href] = norm(a.get_text(" ", strip=True))
    for tag in s.find_all(True):
        for value in tag.attrs.values():
            values=value if isinstance(value,list) else [value]
            for raw in values:
                m=detail_re.search(str(raw or ""))
                if m: links[urljoin(BASE,m.group(0))]=norm(tag.get_text(" ",strip=True))
    return links


def _row_status(text):
    if re.search(r"\bsold\s+prior\b", text or "", re.I): return "SOLD PRIOR"
    if re.search(r"\bwithdrawn(?:\s*-\s*refer)?\b|\bpostponed\b", text or "", re.I): return "WITHDRAWN"
    return "CURRENT"


def _catalogue_rows(s, auction_date):
    lots=[]
    for tr in s.find_all("tr"):
        cells=[norm(td.get_text(" ",strip=True)) for td in tr.find_all(["td","th"])]
        if len(cells)<3: continue
        lot_cell,address=cells[0],cells[1]; lotm=re.fullmatch(r"\s*(\d+[A-Z]?)\s*",lot_cell,re.I)
        if not lotm or len(address)<8: continue
        row_text=norm(" | ".join(cells)); lot_no=lotm.group(1)
        lots.append(Lot(source=SOURCE,url=f"{CURRENT}#lot-{lot_no}",address=address,lot_number=f"Lot {lot_no}",
            auction_date=auction_date,guide_price=parse_guide(row_text),description=row_text,
            property_type="Unclassified catalogue row",status=_row_status(row_text)).finalise())
    return lots


def _fallback_rows(s, auction_date): return _catalogue_rows(s, auction_date)


def _address(s, text):
    for tag in s.find_all(["h1", "h2", "h3"]):
        value = norm(tag.get_text(" ", strip=True))
        if 8 <= len(value) <= 220 and re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", value, re.I): return value
    m = re.search(r"(?:Lot\s*\d+\s*)?([\w&'’.,–\- /]+?\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b)", text or "", re.I)
    return norm(m.group(1)) if m else None


def _target_detail(text):
    """Classify exact particulars, including mixed commercial/residential wording.

    core.is_commercial intentionally fails closed when residential wording is present.
    Barnett Ross often labels genuine mixed-use stock 'Commercial / Residential
    Investment', so explicit mixed/commercial-use evidence must outrank residential
    component words, while ordinary houses/flats still remain excluded.
    """
    low=norm(text).lower()
    explicit=(
        "mixed use","mixed-use","commercial / residential","commercial/residential",
        "commercial and residential","retail and residential","shop and flat","shop with flat",
        "commercial investment","retail investment","ground floor retail","ground-floor retail",
        "commercial unit","retail unit","shop premises","office investment","industrial investment",
        "warehouse","public house","business premises",
    )
    if any(x in low for x in explicit): return True
    return is_commercial(text)


def _property_image(s, base):
    bad=("logo","icon","linkedin","facebook","twitter","staff","team","avatar","ombudsman","rics","cookie","sprite","placeholder"); candidates=[]
    def add(raw,bonus=0):
        if not raw: return
        u=urljoin(base,str(raw).replace("\\/","/").strip(' "\'')); low=u.lower()
        if any(x in low for x in bad) or not re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)", low): return
        score=bonus
        if re.search(r"/details/20\d{6}/\d+\.(?:jpe?g|png|webp)(?:\?|$)",low): score+=40
        if any(x in low for x in ("property","lot","auction","photo","image","upload","picture","pic")): score+=6
        if any(x in low for x in ("large","full","original","1200","1600")): score+=2
        if any(x in low for x in ("thumb","thumbnail","small")): score-=2
        candidates.append((score,u))
    for attrs in ({"property":"og:image"},{"name":"twitter:image"},{"itemprop":"image"}):
        t=s.find("meta",attrs=attrs)
        if t and t.get("content"): add(t.get("content"),15)
    for a in s.find_all("a",href=True):
        label=norm(a.get_text(" ",strip=True)); img=a.find("img"); alt=norm(img.get("alt") or "") if img else ""; combined=(label+" "+alt).lower()
        add(a.get("href"),28 if re.search(r"\bphoto\s*1\b",combined,re.I) else 22 if "photo" in combined else 10)
    for img in s.find_all("img"):
        alt=norm(img.get("alt") or "").lower()
        if any(x in alt for x in bad): continue
        bonus=16 if re.search(r"\bphoto\s*1\b",alt,re.I) else 10 if any(x in alt for x in ("property","lot","external","internal","photo")) else 0
        for attr in ("data-src","data-lazy-src","data-original","data-image","data-url","src"): add(img.get(attr),bonus)
        for attr in ("srcset","data-srcset"):
            raw=img.get(attr)
            if raw:
                for part in raw.split(","): add(part.strip().split(" ")[0],bonus)
    for tag in s.find_all(style=True):
        for raw in re.findall(r'url\(["\']?([^"\')]+)',tag.get("style") or "",re.I): add(raw,8)
    raw_html=str(s).replace("\\/","/")
    for raw in re.findall(r'https?://[^"\'<>\s]+?\.(?:jpe?g|png|webp)(?:\?[^"\'<>\s]*)?',raw_html,re.I): add(raw,4)
    if candidates:
        best={}
        for score,u in candidates: best[u]=max(score,best.get(u,-999))
        winner=max(best.items(),key=lambda kv:(kv[1],-len(kv[0])))
        if winner[1]>0:return winner[0]
    generic=image_from_soup(s,base)
    return generic if generic and not any(x in generic.lower() for x in bad) else None


def _hydrate(url, auction_date=None):
    s=soup(url,use_browser=False); main=s.find("main") or s; text=norm(main.get_text(" ",strip=True)); address=_address(s,text)
    if not address or not _target_detail(text): return None
    status=_row_status(text); lotm=re.search(r"\bLot\s*(\d+[A-Z]?)\b",text,re.I); rent=parse_rent(text); lp_url,lp_status=legal_pack(s,url); title=None
    for tag in s.find_all(["h1","h2","h3"]):
        value=norm(tag.get_text(" ",strip=True))
        if value and value!=address and len(value)<=220:
            title=value
            if any(k in value.lower() for k in ("shop","office","commercial","public house","warehouse","investment","mixed","retail")):break
    return Lot(source=SOURCE,url=url,address=address,lot_number=f"Lot {lotm.group(1)}" if lotm else None,
        auction_date=_parse_date(text) or auction_date,image_url=_property_image(s,url),guide_price=parse_guide(text),annual_rent=rent,
        tenure=parse_tenure(text),vat_status=parse_vat(text),legal_pack_status=lp_status,legal_pack_url=lp_url,description=text[:6500],
        occupation="Tenanted" if rent else ("Vacant / vacant possession" if re.search(r"vacant possession|\bvacant\b",text,re.I) else None),
        property_type=title,development_potential=True if re.search(r"development potential|redevelopment|subject to planning|stpp",text,re.I) else None,
        fri=True if re.search(r"\bFRI\b|full repairing and insuring",text,re.I) else None,status=status).finalise()


def collect():
    try:
        listing=soup(CURRENT,use_browser=False); listing_text=norm(listing.get_text(" ",strip=True)); auction_date=_parse_date(listing_text)
        table_rows=_catalogue_rows(listing,auction_date); targets=_discover(listing)
        # A layout/parser mismatch at one auctioneer must not freeze the entire
        # national production snapshot. Report it explicitly as DEGRADED so the
        # canonical pipeline preserves prior Barnett Ross data instead of treating
        # an empty parse as an authoritative zero or blocking every other source.
        if not table_rows:return SourceResult(SOURCE,"DEGRADED",[],"Barnett Ross current catalogue is reachable but no authoritative catalogue rows were parsed; preserving prior data and publishing other validated sources.",discovered_count=0)
        if not targets:return SourceResult(SOURCE,"DEGRADED",[],f"Barnett Ross published {len(table_rows)} catalogue rows but no exact lot-detail pages were discovered; preserving prior data rather than classifying bare mixed residential/commercial table rows.",discovered_count=0)
        hydrated=[]; failures=0
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures={ex.submit(_hydrate,url,auction_date):url for url in targets}
            for future in as_completed(futures):
                try:
                    lot=future.result()
                    if lot:hydrated.append(lot)
                except Exception:failures+=1
        lots=sorted(hydrated,key=lambda x:(x.lot_number or "",x.address)); terminal=sum(1 for x in lots if x.status in {"SOLD PRIOR","WITHDRAWN"}); current=len(lots)-terminal; excluded=len(table_rows)-len(lots)
        status="DEGRADED" if failures or not lots else "LIVE"
        return SourceResult(SOURCE,status,lots,
            f"Barnett Ross authoritative mixed catalogue: {len(table_rows)} total catalogue rows reconciled; {len(targets)} exact lot-detail pages inspected; {current} live commercial/mixed-use lots; {terminal} sold-prior/withdrawn target lots retained; {excluded} residential/non-target or non-detail rows excluded rather than mislabelled; {failures} detail failures.",
            expected_count=len(lots) if status=="LIVE" else None,discovered_count=len(lots),authoritative_snapshot=bool(status=="LIVE"),scope_dates=tuple(sorted({x.auction_date for x in lots if x.auction_date})))
    except Exception as exc:
        return SourceResult(SOURCE,"DEGRADED",[],f"Barnett Ross collection degraded: {exc}; preserving prior data and publishing other validated sources.")
