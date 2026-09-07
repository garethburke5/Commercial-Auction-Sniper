import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from urllib.parse import urljoin, urlparse, parse_qs

from .core import SourceResult, Lot, norm, is_commercial, parse_guide, parse_rent, parse_tenure, parse_vat
from .utils import soup, detail_lot, image_from_soup, enrich_common_fields

SOURCE = "Future Property Auctions Scotland"
BASE = "https://www.futurepropertyauctions.co.uk"
CATALOGUE = BASE + "/catalogue_viewall.asp"
IMAGE_FEED = BASE + "/zoopla_page_auctions.asp"
PAGE_SIZE = 21
MAX_PAGES = 80
DETAIL_WORKERS = 12


def _parse_date(text):
    value=norm(text);m=re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(20\d{2})\b",value,re.I)
    if not m:return None
    raw=f"{m.group(1)} {m.group(2)} {m.group(3)}"
    for fmt in ("%d %B %Y","%d %b %Y"):
        try:return datetime.strptime(raw,fmt).date()
        except ValueError:pass
    return None


def _commercialish(text):
    low=norm(text).lower()
    return is_commercial(text) or any(x in low for x in ("commercial investment","commercial property","retail investment","ready let investment","portfolio sale","shop and flat","shop with flat","office investment","industrial investment","public house","hotel investment","commercial unit","retail unit","mixed use","mixed-use"))


def _fetch(url):
    try:return soup(url,use_browser=False)
    except Exception:return soup(url,use_browser=True)


def _detail_href(raw):
    href=urljoin(BASE,raw or "").split("#",1)[0];parsed=urlparse(href)
    return href if parsed.netloc.lower().endswith("futurepropertyauctions.co.uk") and parsed.path.lower().endswith("/property_details.asp") and parse_qs(parsed.query).get("id") else None


def _property_id(detail_url):
    try:return parse_qs(urlparse(detail_url or "").query).get("id",[None])[0]
    except Exception:return None


def _listing_card(anchor,max_chars=1800):
    node=anchor;best=norm(anchor.get_text(" ",strip=True))
    for _ in range(8):
        node=getattr(node,"parent",None)
        if node is None:break
        text=norm(node.get_text(" ",strip=True))
        if not text or len(text)>max_chars:break
        ids={_detail_href(a.get("href")) for a in node.find_all("a",href=True)};ids.discard(None)
        if len(ids)>1:break
        if len(text)>len(best):best=text
    return best


def _page_urls(s,current_url):
    out=[]
    for a in s.find_all("a",href=True):
        href=urljoin(current_url,a.get("href") or "").split("#",1)[0];p=urlparse(href)
        if not p.netloc.lower().endswith("futurepropertyauctions.co.uk") or not p.path.lower().endswith("/catalogue_viewall.asp"):continue
        qs=parse_qs(p.query)
        if "offset" in qs:
            try:
                if int(qs["offset"][0])>=0 and href not in out:out.append(href)
            except Exception:pass
    return out


def _is_property_photo_url(raw,expected_id=None):
    if not raw:return False
    u=urljoin(BASE,str(raw));p=urlparse(u);low=u.lower()
    if not (p.hostname or "").lower().endswith("futurepropertyauctions.co.uk"):return False
    if not any(x in p.path.lower() for x in ("/upload/","/uploads/","/property_images/","/property-images/")):return False
    if any(x in low for x in ("logo","icon","sprite","placeholder","floorplan","floor-plan","map","epc","social","spacer","banner")):return False
    if not re.search(r"\.(?:jpe?g|png|webp)(?:\?|$)",low):return False
    if expected_id:
        token=str(expected_id).lower();filename=p.path.rsplit("/",1)[-1].lower()
        if token not in filename and f"/{token}/" not in p.path.lower():return False
    return True


def _feed_image_map(fetcher=_fetch):
    """Map property IDs to hero photos from FPA's own public property export.

    The normal catalogue frequently lazy-loads/no-renders photos in GitHub Actions,
    while the first-party export contains canonical /upload/..._<property id>_IMG_00
    URLs. This is association-safe because the property ID is embedded in the image.
    """
    try:raw=str(fetcher(IMAGE_FEED)).replace("\\/","/")
    except Exception:return {}
    out={}
    urls=re.findall(r'https?://[^|"\'<>\s]+?/upload/[^|"\'<>\s]+?\.(?:jpe?g|png|webp)',raw,re.I)
    for u in urls:
        m=re.search(r"_(\d{5,})_IMG_00\.(?:jpe?g|png|webp)$",u,re.I)
        if not m:continue
        pid=m.group(1)
        if _is_property_photo_url(u,pid):out.setdefault(pid,u)
    return out


def _card_image(anchor,page_url):
    expected_id=_property_id(_detail_href(anchor.get("href")));node=anchor
    for _ in range(7):
        node=getattr(node,"parent",None)
        if node is None:break
        text=norm(node.get_text(" ",strip=True))
        if len(text)>2600:break
        ids={_detail_href(a.get("href")) for a in node.find_all("a",href=True)};ids.discard(None)
        if len(ids)>1:break
        linked=[]
        for a in node.find_all("a",href=True):
            if _is_property_photo_url(a.get("href"),expected_id):linked.append(urljoin(page_url,a.get("href")))
        if linked:
            linked.sort(key=lambda u:("_img_00" in u.lower(),"small_" not in u.lower(),len(u)),reverse=True);return linked[0]
        try:
            img=image_from_soup(node,page_url)
            if img and _is_property_photo_url(img,expected_id):return img
        except Exception:pass
        # Some cards inject galleries through CSS/JSON rather than <img>.
        raw=str(node).replace("\\/","/")
        for u in re.findall(r'(?:https?://[^"\'<>\s]+|/[A-Za-z0-9_./-]+)\.(?:jpe?g|png|webp)',raw,re.I):
            full=urljoin(page_url,u)
            if _is_property_photo_url(full,expected_id):return full
    return None


def _detail_image(s,detail_url):
    expected_id=_property_id(detail_url);candidates=[]
    for a in s.find_all("a",href=True):
        if _is_property_photo_url(a.get("href"),expected_id):candidates.append(urljoin(detail_url,a.get("href")))
    for img in s.find_all("img"):
        for attr in ("data-src","data-lazy-src","data-original","src"):
            if _is_property_photo_url(img.get(attr),expected_id):candidates.append(urljoin(detail_url,img.get(attr)))
    raw=str(s).replace("\\/","/")
    for u in re.findall(r'(?:https?://[^"\'<>\s]+|/[A-Za-z0-9_./-]+)\.(?:jpe?g|png|webp)',raw,re.I):
        full=urljoin(detail_url,u)
        if _is_property_photo_url(full,expected_id):candidates.append(full)
    if candidates:
        candidates=list(dict.fromkeys(candidates));candidates.sort(key=lambda u:("_img_00" in u.lower(),"small_" not in u.lower(),len(u)),reverse=True);return candidates[0]
    generic=image_from_soup(s,detail_url)
    return generic if generic and _is_property_photo_url(generic,expected_id) else None


def _card_address(anchor,card):
    node=anchor
    for _ in range(6):
        if node is None:break
        ids={_detail_href(a.get("href")) for a in node.find_all("a",href=True)};ids.discard(None)
        if len(ids)>1:break
        for a in node.find_all("a",href=True):
            if "maps.google" in (a.get("href") or "").lower():
                val=norm(a.get_text(" ",strip=True))
                if 6<=len(val)<=240:return val
        text=norm(node.get_text(" ",strip=True))
        if len(text)>2400:break
        node=getattr(node,"parent",None)
    value=norm(card);value=re.sub(r"^Lot\s+\d+[A-Z]?\s+£[\d,]+\s+(?:OPENING BID|GUIDE PRICE)?\s*","",value,flags=re.I);value=re.sub(r"^(?:Commercial Investment|Commercial Property|Retail Investment|Ready Let Investment|Mixed[- ]Use)\s+","",value,flags=re.I);value=re.split(r"\b(?:Timed Online Auction|Auction Date)\b",value,1,flags=re.I)[0]
    return norm(value)[:240] or None


def _fallback_lot(href,card,anchor,auction_date,page_url):
    address=_card_address(anchor,card)
    if not address:return None
    m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I);low=card.lower();ptype="Mixed Use" if "mixed use" in low or "mixed-use" in low else "Retail Investment" if "retail investment" in low else "Commercial Investment" if "commercial investment" in low else "Commercial"
    lot=Lot(source=SOURCE,url=href,address=address,lot_number=f"Lot {m.group(1)}" if m else None,auction_date=auction_date,image_url=_card_image(anchor,page_url),guide_price=parse_guide(card),annual_rent=parse_rent(card),tenure=parse_tenure(card),vat_status=parse_vat(card),property_type=ptype,description=card,status="CURRENT")
    return enrich_common_fields(lot,card).finalise()


def _discover(fetcher=_fetch,today=None):
    today=today or date.today();targets={};dates_seen=set();future_urls=set();pages_read=0;queue=[CATALOGUE];queued={CATALOGUE};fallback_offset=0
    while queue and pages_read<MAX_PAGES:
        url=queue.pop(0);s=fetcher(url);pages_read+=1;detail_found=0
        for a in s.find_all("a",href=True):
            href=_detail_href(a.get("href"))
            if not href:continue
            detail_found+=1;card=_listing_card(a);auction_date=_parse_date(card)
            if not auction_date or auction_date<today:continue
            future_urls.add(href);dates_seen.add(auction_date.isoformat())
            if not _commercialish(card):continue
            m=re.search(r"\bLot\s+(\d+[A-Z]?)\b",card,re.I);targets[href]=(card,f"Lot {m.group(1)}" if m else None,auction_date.isoformat(),a,url)
        for next_url in _page_urls(s,url):
            if next_url not in queued and len(queued)<MAX_PAGES:queued.add(next_url);queue.append(next_url)
        if not queue and detail_found>=PAGE_SIZE and pages_read<MAX_PAGES:
            fallback_offset+=PAGE_SIZE;next_url=f"{CATALOGUE}?offset={fallback_offset}"
            if next_url not in queued:queued.add(next_url);queue.append(next_url)
    return targets,tuple(sorted(dates_seen)),len(future_urls),pages_read


def _hydrate_target(href,payload,feed_images=None):
    card,lot_number,auction_date,anchor,page_url=payload;lot=None
    for use_browser in (False,True):
        try:
            lot=detail_lot(SOURCE,href,seed=card,lot_number=lot_number,auction_date=auction_date,force_commercial=True,use_browser=use_browser,suppress_prior=True)
            if lot:break
        except Exception:pass
    expected_id=_property_id(href);source_image=None
    if lot and _is_property_photo_url(lot.image_url,expected_id):source_image=lot.image_url
    if not source_image:source_image=_card_image(anchor,page_url)
    if not source_image:
        try:source_image=_detail_image(_fetch(href),href)
        except Exception:pass
    if not source_image and feed_images:source_image=feed_images.get(str(expected_id))
    if lot:
        lot.image_url=source_image;return lot.finalise(),False
    fallback=_fallback_lot(href,card,anchor,auction_date,page_url)
    if fallback and source_image:fallback.image_url=source_image
    return fallback,True if fallback else False


def collect():
    try:
        targets,scope_dates,discovered_future,pages_read=_discover();lots=[];failures=0;fallbacks=0;feed_images=_feed_image_map()
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
            futures={ex.submit(_hydrate_target,href,payload,feed_images):href for href,payload in targets.items()}
            for future in as_completed(futures):
                try:
                    lot,used_fallback=future.result()
                    if lot:lots.append(lot);fallbacks+=int(used_fallback)
                    else:failures+=1
                except Exception:failures+=1
        expected=len(targets)
        if expected:
            status="LIVE" if failures==0 and len(lots)==expected else "DEGRADED";images=sum(1 for x in lots if x.image_url)
            return SourceResult(SOURCE,status,lots,f"All-future Future Property Auctions sweep: {pages_read} catalogue pages inspected; {discovered_future} unique future catalogue lots encountered across dates {scope_dates}; {expected} commercial/mixed-use targets discovered; {len(lots)} captured; lot-bound property images {images}/{len(lots)} ({len(feed_images)} first-party export hero mappings available); {fallbacks} authoritative catalogue-card fallbacks; {failures} unrecovered detail failures.",expected_count=expected,discovered_count=expected,authoritative_snapshot=bool(status=="LIVE"),scope_dates=scope_dates)
        if discovered_future:return SourceResult(SOURCE,"CATALOGUE PENDING",[],f"Future Property Auctions catalogue inspected across {pages_read} pages; {discovered_future} unique future lots encountered across dates {scope_dates}, but none classified commercial/mixed-use.",expected_count=0,discovered_count=0,authoritative_snapshot=True,scope_dates=scope_dates)
        return SourceResult(SOURCE,"CATALOGUE PENDING",[],f"Future Property Auctions catalogue inspected across {pages_read} pages; no published future lots were discovered.",discovered_count=0,authoritative_snapshot=False,scope_dates=scope_dates)
    except Exception as exc:return SourceResult(SOURCE,"FAILED",[],f"Future Property Auctions collection failed: {type(exc).__name__}: {exc}")
