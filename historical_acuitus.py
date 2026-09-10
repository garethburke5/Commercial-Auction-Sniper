from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collectors import acuitus
from collectors.core import norm
from history_database import update_history_database, load_database

BASE = "https://www.acuitus.co.uk"
RESULTS_URL = BASE + "/find-a-property/?which=results"
DATA = Path("data")
PROGRESS_PATH = DATA / "historical_backfill_progress.json"
HISTORY_PATH = DATA / "property_history.json"
DATE_RE = re.compile(r"\b(\d{2})/(\d{2})/(20\d{2})\b")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_progress():
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"schema_version": 1, "updated_at": None, "sources": {}}
    data.setdefault("schema_version", 1)
    data.setdefault("sources", {})
    return data


def save_progress(progress):
    DATA.mkdir(exist_ok=True)
    progress["updated_at"] = now_iso()
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False), encoding="utf-8")


def iso_date(text):
    m = DATE_RE.search(text or "")
    if not m:
        return None
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


def _get(session, url, **kwargs):
    r = session.get(url, timeout=40, **kwargs)
    r.raise_for_status()
    return r


def discover_auctions(session):
    r = _get(session, RESULTS_URL)
    s = BeautifulSoup(r.text, "lxml")
    candidates = []
    chosen = None
    for select in s.find_all("select"):
        opts = []
        for opt in select.find_all("option"):
            text = norm(opt.get_text(" ", strip=True))
            dt = iso_date(text)
            if dt:
                opts.append((dt, opt.get("value"), text))
        if len(opts) > len(candidates):
            candidates = opts
            chosen = select
    if not candidates or chosen is None:
        # Acuitus currently renders the auction selector server-side. Refuse to
        # guess or mark caught-up if that first-party archive disappears.
        raise RuntimeError("Acuitus results page exposed no historical auction-date selector")

    # Acuitus represents the newest completed sale with a special "Last Auction"
    # option rather than a dated option. Derive that date only from the
    # authoritative results currently rendered on the same first-party page,
    # then bind it to the site's actual selector value. This prevents the newest
    # completed auction from being silently omitted from historical coverage.
    last_opt = next(
        (opt for opt in chosen.find_all("option") if norm(opt.get_text(" ", strip=True)).lower() == "last auction"),
        None,
    )
    if last_opt is not None:
        rendered_dates = []
        for text in s.stripped_strings:
            clean = norm(text)
            if "Auction" not in clean:
                continue
            dt = iso_date(clean)
            if dt:
                rendered_dates.append(dt)
        if rendered_dates:
            last_date = max(rendered_dates)
            if all(dt != last_date for dt, _, _ in candidates):
                candidates.append((last_date, last_opt.get("value"), "Last Auction"))

    form = chosen.find_parent("form")
    if form is None or not chosen.get("name"):
        raise RuntimeError("Acuitus auction selector has no submit form/name")
    action = urljoin(r.url, form.get("action") or r.url)
    method = (form.get("method") or "get").lower()
    base_fields = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        typ = (inp.get("type") or "text").lower()
        if not name or typ in {"submit", "button", "image", "file"}:
            continue
        if typ in {"checkbox", "radio"} and not inp.has_attr("checked"):
            continue
        base_fields[name] = inp.get("value") or ""
    base_fields.setdefault("which", "results")
    auctions = []
    seen = set()
    for dt, value, label in sorted(candidates, reverse=True):
        if dt in seen:
            continue
        seen.add(dt)
        auctions.append({
            "auction_date": dt,
            "label": label,
            "select_name": chosen.get("name"),
            "select_value": value if value not in (None, "") else label,
            "form_action": action,
            "form_method": method,
            "base_fields": base_fields,
            "source_index_url": RESULTS_URL,
        })
    return auctions


def fetch_auction_page(session, auction):
    data = dict(auction["base_fields"])
    data[auction["select_name"]] = auction["select_value"]
    if auction["form_method"] == "post":
        r = session.post(auction["form_action"], data=data, timeout=45)
    else:
        r = session.get(auction["form_action"], params=data, timeout=45)
    r.raise_for_status()
    s = BeautifulSoup(r.text, "lxml")
    return r.url, s


def _money(text):
    m = re.search(r"£\s*([\d,]+(?:\.\d+)?)", text or "")
    return float(m.group(1).replace(",", "")) if m else None


def _yield(text):
    m = re.search(r"(?:Yield[^\d]{0,20})?(\d{1,2}(?:\.\d+)?)\s*%", text or "", re.I)
    return float(m.group(1)) if m else None


def _status(text):
    m = re.search(r"\bStatus\s+(Sold Prior|Sold Post|Sold|Withdrawn Prior|Withdrawn Post|Withdrawn|Deferred|Available|Unsold)\b", text or "", re.I)
    return norm(m.group(1)).upper() if m else "ARCHIVED"


def _property_links(page_soup, auction_date):
    seen = set()
    out = []
    display_date = datetime.strptime(auction_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    for a in page_soup.find_all("a", href=True):
        href = urljoin(BASE, a["href"]).split("?", 1)[0]
        if not re.search(r"/property/\d+/?$", href, re.I) or href in seen:
            continue
        # nearest_card includes status/price/yield shown by the authoritative results table.
        card = acuitus.nearest_card(a, 5000)
        if display_date not in card:
            continue
        seen.add(href)
        out.append((href, card))
    return out


def _row(session, href, card, auction_date):
    # Reuse the production rich Acuitus parser for tenancy, rent, tenure, lease,
    # area and evidence facts, but bind the event to its actual historical auction.
    lot = acuitus._rich_lot(href, card).to_dict()
    lot["auction_date"] = auction_date
    lot["status"] = _status(card)
    lot["gross_yield"] = _yield(card) or lot.get("gross_yield")
    price_text = re.search(r"\bPrice\*?\s*([^|]{0,80})", card, re.I)
    if price_text:
        lot["sale_price"] = _money(price_text.group(1))
    else:
        lot["sale_price"] = _money(card) if "sold" in lot["status"].lower() else None
    pid = re.search(r"/property/(\d+)/?", href, re.I)
    lot["source_id"] = pid.group(1) if pid else None
    lot["evidence_url"] = href
    lot["url"] = href
    return lot


def backfill_acuitus(max_auctions=6, oldest_year=None):
    progress = load_progress()
    state = progress["sources"].setdefault("Acuitus", {
        "status": "NOT STARTED", "auctions_discovered": 0, "auctions_completed": 0,
        "lots_captured": 0, "earliest_month_reached": None, "completed_auction_ids": [], "failures": [],
    })
    session = _session()
    try:
        auctions = discover_auctions(session)
    except Exception as exc:
        state["status"] = "DEGRADED"
        failure = {"error": f"{type(exc).__name__}: {exc}", "at": now_iso()}
        state.setdefault("failures", []).append(failure)
        state["last_failure"] = failure
        state["last_run_failures"] = 1
        state["last_run_rows"] = 0
        state["last_run"] = now_iso()
        save_progress(progress)
        return {"source": "Acuitus", "rows": 0, "state": state}

    state["auctions_discovered"] = len(auctions)
    completed = set(state.get("completed_auction_ids") or [])
    selected = []
    for a in auctions:
        aid = a["auction_date"]
        if aid in completed:
            continue
        if oldest_year and int(aid[:4]) < oldest_year:
            continue
        selected.append(a)
        if len(selected) >= max_auctions:
            break
    state["status"] = "RUNNING" if selected else "CAUGHT UP"
    state["last_run_auctions_selected"] = len(selected)
    save_progress(progress)

    rows_this_run = 0
    failures_this_run = 0
    for auction in selected:
        aid = auction["auction_date"]
        state["last_attempt"] = {"auction_id": aid, "label": auction["label"], "at": now_iso()}
        save_progress(progress)
        try:
            page_url, page = fetch_auction_page(session, auction)
            links = _property_links(page, aid)
            if not links:
                raise RuntimeError(f"Acuitus archive returned zero property links for {aid} ({page_url})")
            rows = []
            detail_failures = []
            for href, card in links:
                try:
                    rows.append(_row(session, href, card, aid))
                except Exception as exc:
                    detail_failures.append(f"{href}: {type(exc).__name__}: {exc}")
            if detail_failures:
                raise RuntimeError(f"{len(detail_failures)}/{len(links)} detail pages failed; first={detail_failures[0]}")
            if len(rows) != len(links):
                raise RuntimeError(f"Acuitus completeness mismatch: {len(links)} archive links vs {len(rows)} rows")
            db = update_history_database(rows, path=HISTORY_PATH)
            rows_this_run += len(rows)
            completed.add(aid)
            state["completed_auction_ids"] = sorted(completed)
            state["auctions_completed"] = len(completed)
            state["lots_captured"] = int(state.get("lots_captured") or 0) + len(rows)
            month = aid[:7]
            earliest = state.get("earliest_month_reached")
            state["earliest_month_reached"] = min(earliest, month) if earliest else month
            state["last_success_rows"] = len(rows)
            state["last_expected_lots"] = len(links)
            state["last_discovery_mode"] = "acuitus-first-party-results-form"
            state["last_history_event_count"] = len(db.get("auction_events") or [])
            state["last_success"] = now_iso()
            state["status"] = "RUNNING"
            save_progress(progress)
        except Exception as exc:
            failures_this_run += 1
            failure = {"auction_id": aid, "label": auction["label"], "error": f"{type(exc).__name__}: {exc}", "at": now_iso()}
            state.setdefault("failures", []).append(failure)
            state["last_failure"] = failure
            state["status"] = "DEGRADED"
            save_progress(progress)
            # Do not skip past a broken auction: chronological completeness matters.
            break

    remaining = [a for a in auctions if a["auction_date"] not in completed]
    if not remaining and not failures_this_run:
        state["status"] = "CAUGHT UP"
    elif failures_this_run:
        state["status"] = "DEGRADED"
    state["last_run_rows"] = rows_this_run
    state["last_run_failures"] = failures_this_run
    state["last_run"] = now_iso()
    save_progress(progress)
    return {"source": "Acuitus", "rows": rows_this_run, "state": state}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-auctions", type=int, default=6)
    ap.add_argument("--oldest-year", type=int, default=None)
    args = ap.parse_args()
    result = backfill_acuitus(max_auctions=args.max_auctions, oldest_year=args.oldest_year)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["state"].get("last_run_failures"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
