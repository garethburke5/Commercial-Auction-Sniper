"""EIG Passport / legal-document client for Auction Sniper.

Credentials are read by the caller from Streamlit secrets and are never stored here.
The client intentionally discovers the live login form rather than persisting secToken URLs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PASSPORT = "https://passport.eigroup.co.uk/"
LEGAL = "https://legaldocuments.eigroup.co.uk/"
UA = "Mozilla/5.0 (compatible; AuctionSniper/6.62; +legal-pack-reader)"


@dataclass
class EIGDocument:
    name: str
    url: str
    updated: str | None = None
    size: str | None = None
    priority: int = 50


def document_priority(name: str) -> int:
    n = (name or "").lower()
    groups = [
        (0, ("special condition",)),
        (5, ("lease", "tenancy", "agreement for lease")),
        (10, ("cpse", "commercial property standard enquiries")),
        (12, ("judgment", "court", "consent order", "dispute", "proceedings")),
        (15, ("official copy", "register", "title")),
        (20, ("vat", "option to tax", "ott")),
        (22, ("epc", "energy performance")),
        (30, ("tp1", "transfer")),
        (70, ("local search", "chancel", "utility", "electricity", "gas", "openreach")),
        (80, ("plan", "risk assessment")),
    ]
    for score, words in groups:
        if any(w in n for w in words):
            return score
    return 50


class EIGClient:
    def __init__(self, email: str, password: str, timeout: int = 20):
        self.email = email
        self.password = password
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})

    def _get(self, url, **kw):
        r = self.s.get(url, timeout=self.timeout, allow_redirects=True, **kw)
        r.raise_for_status()
        return r

    def login(self) -> bool:
        """Authenticate through EIG's current Passport form.

        Field names and hidden anti-CSRF values are discovered from the returned HTML,
        avoiding hard-coded temporary security tokens.
        """
        r = self._get(PASSPORT)
        soup = BeautifulSoup(r.text, "lxml")
        form = soup.find("form")
        if not form:
            return False
        action = urljoin(r.url, form.get("action") or r.url)
        payload = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                payload[name] = inp.get("value", "")
        names = list(payload)
        email_field = next((n for n in names if any(x in n.lower() for x in ("email", "username", "user"))), None)
        pass_field = next((n for n in names if "pass" in n.lower()), None)
        if not email_field or not pass_field:
            return False
        payload[email_field] = self.email
        payload[pass_field] = self.password
        method = (form.get("method") or "post").lower()
        if method == "get":
            out = self.s.get(action, params=payload, timeout=self.timeout, allow_redirects=True)
        else:
            out = self.s.post(action, data=payload, timeout=self.timeout, allow_redirects=True)
        out.raise_for_status()
        low = out.text.lower()
        return not ("forgotten password" in low and "sign in" in low and "password" in low)

    def pack(self, pack_id: int | str) -> tuple[str, list[EIGDocument]]:
        url = urljoin(LEGAL, f"showbyid/{pack_id}")
        r = self._get(url)
        # If redirected to Passport, authenticate then retry the pack URL.
        if "passport.eigroup.co.uk" in r.url.lower() or "sign in to passport" in r.text.lower():
            if not self.login():
                raise RuntimeError("EIG Passport authentication failed")
            r = self._get(url)
        soup = BeautifulSoup(r.text, "lxml")
        title = ""
        h = soup.find(["h1", "h2"])
        if h:
            title = " ".join(h.stripped_strings)
        docs = []
        seen = set()
        for a in soup.find_all("a", href=True):
            label = " ".join(a.stripped_strings).strip()
            href = urljoin(r.url, a["href"])
            context = " ".join((a.parent or a).stripped_strings)
            # Legal pack download links are identified by document-like labels/context;
            # exclude navigation and generic conditions links.
            looks_doc = bool(re.search(r"\.(?:pdf|docx?|png|jpe?g)\b", label, re.I)) or "document:" in context.lower()
            if not looks_doc or href in seen:
                continue
            seen.add(href)
            name = re.sub(r"^Document:\s*", "", label, flags=re.I).strip() or context[:180]
            um = re.search(r"Last Updated:\s*([^\n]+?)(?:Downloaded:|$)", context, re.I)
            sm = re.search(r"File Size:\s*([^\n]+?)(?:Last Updated:|Downloaded:|$)", context, re.I)
            docs.append(EIGDocument(name=name, url=href,
                                    updated=um.group(1).strip() if um else None,
                                    size=sm.group(1).strip() if sm else None,
                                    priority=document_priority(name)))
        docs.sort(key=lambda d: (d.priority, d.name.lower()))
        return title, docs

    def download(self, doc: EIGDocument) -> bytes:
        r = self._get(doc.url)
        return r.content
