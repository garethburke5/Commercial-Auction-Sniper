import re
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .browser import get_html
from .core import SourceResult, parse_guide, parse_rent, parse_tenure, parse_vat, norm
from .savills import SOURCE, BASE, UPCOMING, _auction_dates, _discover_commercial_feed, _detail, _detail_href, _lot_no


def _calendar_html(timeout=30):
    """Read the Savills auction calendar from independent first-party routes.

    The dedicated /upcoming-auctions endpoint intermittently stalls from hosted
    runners even when the Savills home page is healthy and contains the same
    current/future catalogue links. Do not let one route/protocol failure erase
    an otherwise public catalogue.
    """
    errors=[]
    for url in (UPCOMING, BASE + "/", BASE + "/home", BASE + "/index.php"):
        try:
            html=get_html(url, use_browser=False, timeout_ms=timeout * 1000)
            if html and re.search(r"/auctions/[^/]+-\d+", html, re.I):
                return html
            errors.append(f"{url}: no auction links")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
    raise RuntimeError("Savills calendar routes unavailable: " + "; ".join(errors))


def _discover_all_future_auctions(html=None):
    if html is None:
        html = _calendar_html()
    soup = BeautifulSoup(html, "lxml")
    today = date.today()
    auctions = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE, a.get("href") or "").split("?")[0].rstrip("/")
        if not re.search(r"/auctions/[^/]+-\d+$", href, re.I):
            continue
        node = a
        card = a.get_text(" ", strip=True)
        for _ in range(6):
            node = getattr(node, "parent", None)
            if node is None:
                break
            text = node.get_text(" ", strip=True)
            if 10 <= len(text) <= 3000:
                card = text
                if re.search(r"20\d{2}", text):
                    break
        start, end = _auction_dates(card, href)
        if start and end and end >= today:
            auctions[href] = {"catalogue": href, "start": start, "end": end, "label": card}
    return [auctions[k] for k in sorted(auctions, key=lambda u: (auctions[u]["start"], u))]


def _normalise_savills_asset(value, href):
    """Normalise first-party Savills lot-image representations into usable URLs.

    Savills currently emits genuine gallery photos inside script data as
    /images/lots/<auction>/<lot>/<hash>.jpeg. Older/current variants also use
    /assets/images/lots/ and dedicated lot-image routes. All accepted patterns
    are lot-scoped; brand, map and generic auction assets are deliberately excluded.
    """
    if not value:
        return None
    value = str(value).replace("\\/", "/").replace("&amp;", "&").strip("\"' ")
    low = value.lower()
    markers = ("/images/lots/", "/assets/images/lots/", "/lot-images/", "/lot-image/")
    if not any(marker in low for marker in markers):
        return None
    if value.startswith("//"):
        return "https:" + value
    if value.startswith(("/images/lots/", "images/lots/")):
        return urljoin(BASE + "/", value)
    if value.startswith("/assets/images/lots/"):
        return "https://resize.auctions.savills.co.uk" + value
    if value.startswith("assets/images/lots/"):
        return "https://resize.auctions.savills.co.uk/" + value
    if value.startswith(("http://", "https://")):
        return value
    return urljoin(href, value)


def _savills_property_image_from_html(raw, href):
    raw = (raw or "").replace("\\/", "/")
    candidates = []
    token_re = r'(?:https?:)?//[^"\'<>\s,]+|/(?:assets/)?images/lots/[^"\'<>\s,]+|(?:assets/)?images/lots/[^"\'<>\s,]+|/lot-images?/[^"\'<>\s,]+'
    for token in re.findall(token_re, raw, re.I):
        u = _normalise_savills_asset(token, href)
        if u:
            u = re.sub(r"[)\]}]+$", "", u)
            if u not in candidates:
                candidates.append(u)
    if candidates:
        return candidates[0]

    s = BeautifulSoup(raw, "lxml")
    scored = []
    for img in s.find_all("img"):
        values = [img.get("data-src"), img.get("data-lazy-src"), img.get("data-original"), img.get("src")]
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            values.extend(part.strip().split(" ", 1)[0] for part in srcset.split(","))
        for src in values:
            u = _normalise_savills_asset(src, href)
            if not u:
                continue
            low = u.lower()
            alt = norm(img.get("alt") or "").lower()
            score = 100
            if "resize.auctions.savills.co.uk" in low:
                score += 40
            if any(x in alt for x in ("property", "lot", "auction")):
                score += 5
            scored.append((score, u))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1] if scored else None


def _savills_property_image(href):
    """Return a real Savills lot photograph, never a brand/placeholder tile."""
    try:
        raw = get_html(href, use_browser=False, timeout_ms=20000)
    except Exception:
        try:
            raw = get_html(href, use_browser=True, timeout_ms=25000)
        except Exception:
            return None
    return _savills_property_image_from_html(raw, href)


def _catalogue_images(feed):
    """Map detail URLs to the image in their catalogue card."""
    if not feed:
        return {}
    try:
        raw = get_html(feed, use_browser=False, timeout_ms=25000)
    except Exception:
        try:
            raw = get_html(feed, use_browser=True, timeout_ms=30000)
        except Exception:
            return {}
    s = BeautifulSoup(raw, "lxml")
    out = {}
    for a in s.find_all("a", href=True):
        detail = _detail_href(a)
        if not detail or detail in out:
            continue
        node = a
        chosen = None
        for _ in range(8):
            node = getattr(node, "parent", None)
            if node is None:
                break
            text = norm(node.get_text(" ", strip=True))
            if len(text) > 3500:
                break
            if _lot_no(text) is None:
                continue
            chosen = _savills_property_image_from_html(str(node), feed)
            if chosen:
                break
        if chosen:
            out[detail] = chosen
    return out


def _repair_from_catalogue(lot, meta, href):
    """Preserve first-party catalogue evidence when detail HTML is partially hydrated."""
    card = norm((meta or {}).get("card") or "")
    if not lot.guide_price:
        lot.guide_price = parse_guide(card)
    if not lot.annual_rent:
        lot.annual_rent = parse_rent(card)
    if not lot.tenure:
        lot.tenure = parse_tenure(card)
    if lot.vat_status in (None, "", "UNKNOWN"):
        lot.vat_status = parse_vat(card)
    if card and card.lower() not in (lot.description or "").lower():
        lot.description = norm(card + " " + (lot.description or ""))[:9000]

    img = _savills_property_image(href) or (meta or {}).get("image_url")
    if img:
        lot.image_url = img
    else:
        low = (lot.image_url or "").lower()
        if any(x in low for x in ("logo", "savills-logo", "brand", "social", "placeholder")) or not any(
            marker in low for marker in ("/images/lots/", "/assets/images/lots/", "/lot-images/", "/lot-image/")
        ):
            lot.image_url = None
    return lot.finalise()


def collect():
    try:
        auctions = _discover_all_future_auctions()
    except Exception as exc:
        return SourceResult(SOURCE, "FAILED", [], f"Could not read Savills auction calendar: {type(exc).__name__}: {exc}")
    if not auctions:
        return SourceResult(SOURCE, "FAILED", [], "No current/future Savills auction catalogues discovered")

    lots_by_url = {}
    expected = discovered = failures = published_catalogues = pending_catalogues = 0
    scopes = set()
    notes = []
    for auction in auctions:
        scopes.add(auction["start"].isoformat())
        scopes.add(auction["end"].isoformat())
        try:
            feed, targets = _discover_commercial_feed(auction)
        except Exception as exc:
            failures += 1
            notes.append(f"{auction['start'].isoformat()}: feed error {type(exc).__name__}")
            continue
        if not targets:
            pending_catalogues += 1
            notes.append(f"{auction['start'].isoformat()}: no commercial lots published")
            continue

        card_images = _catalogue_images(feed)
        for href, meta in targets.items():
            if href in card_images:
                meta["image_url"] = card_images[href]

        published_catalogues += 1
        expected += len(targets)
        discovered += len(targets)
        catalogue_failures = 0
        for href, meta in targets.items():
            try:
                lot = _detail(href, auction, source_commercial=True)
                if lot:
                    lots_by_url[href] = _repair_from_catalogue(lot, meta, href)
                else:
                    catalogue_failures += 1
            except Exception as exc:
                catalogue_failures += 1
                print("SAVILLS_ALL_FUTURE_DETAIL_FAIL", href, repr(exc))
        failures += catalogue_failures
        notes.append(
            f"{auction['start'].isoformat()}: {len(targets)} commercial discovered, "
            f"{len([u for u in targets if u in lots_by_url])} published, {len(card_images)} card images mapped"
        )

    lots = list(lots_by_url.values())
    if expected and len(lots) == expected and failures == 0:
        status = "LIVE"
    elif lots:
        status = "DEGRADED"
    elif pending_catalogues and failures == 0:
        status = "CATALOGUE PENDING"
    else:
        status = "FAILED"
    return SourceResult(
        SOURCE,
        status,
        lots,
        f"All-future Savills sweep: {len(auctions)} future catalogue(s), {published_catalogues} with commercial inventory, "
        f"{pending_catalogues} pending; {discovered} commercial lots discovered, {len(lots)} published, {failures} failures. "
        + "; ".join(notes),
        expected_count=expected or None,
        discovered_count=discovered,
        authoritative_snapshot=bool(status == "LIVE" and expected and len(lots) == expected),
        scope_dates=tuple(sorted(scopes)),
    )
