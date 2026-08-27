from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
import hashlib
import re
from urllib.parse import urljoin

MONEY_RE = re.compile(r"£\s*([\d,]+(?:\.\d{1,2})?)")

COMMERCIAL_TERMS = [
    "commercial property","commercial unit","commercial building","commercial investment",
    "retail property","retail unit","retail investment","retail building","retail premises",
    "shop investment","shop and flat","shop with flat","ground floor shop","ground-floor shop",
    "office property","office building","office investment","office premises","office unit",
    "industrial unit","industrial property","industrial investment","warehouse","workshop","factory",
    "trade counter","business premises","business unit","restaurant","takeaway","public house",
    "pub investment","hotel","care home","day nursery","supermarket","pharmacy","showroom",
    "commercial depot","mixed use","mixed-use","commercial/residential","commercial and residential",
    "retail and residential","shopping centre","retail park","leisure investment",
    "advertising display site","ground rent investment"
]
RESIDENTIAL_ONLY = [
    "residential flat","one bedroom flat","two bedroom flat","three bedroom flat",
    "apartment","maisonette","bungalow","detached house","semi-detached",
    "terraced house","end terraced house","family home","dwelling house",
    "retirement flat","studio flat","residential investment","town house",
    "three-bedroom house","two-bedroom house","four-bedroom house"
]
MIXED_MARKERS = [
    "mixed use","mixed-use","commercial/residential","commercial and residential",
    "shop and flat","shop with flat","retail and residential"
]

@dataclass
class Lot:
    source: str
    url: str
    address: str
    lot_number: Optional[str] = None
    auction_date: Optional[str] = None
    image_url: Optional[str] = None
    guide_price: Optional[float] = None
    annual_rent: Optional[float] = None
    gross_yield: Optional[float] = None
    tenure: Optional[str] = None
    vat_status: str = "UNKNOWN"
    legal_pack_status: str = "UNKNOWN"
    legal_pack_url: Optional[str] = None
    status: str = "Live"
    description: str = ""
    collected_at: str = ""

    def finalise(self):
        if self.guide_price and self.annual_rent:
            self.gross_yield = round(self.annual_rent / self.guide_price * 100, 2)
        else:
            self.gross_yield = None
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()
        return self

    @property
    def source_id(self):
        return hashlib.sha1(f"{self.source}|{self.url}".encode()).hexdigest()

    def to_dict(self):
        d = asdict(self.finalise())
        d["source_id"] = self.source_id
        return d

@dataclass
class SourceResult:
    source: str
    status: str
    lots: list[Lot]
    message: str = ""

    def to_status_dict(self):
        return {
            "source": self.source,
            "status": self.status,
            "lots_seen": len(self.lots),
            "message": self.message,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()

def parse_money(text):
    m = MONEY_RE.search(str(text or ""))
    return float(m.group(1).replace(",", "")) if m else None

def parse_guide(text):
    for pat in [
        r"Guide Price(?:\s*[:*])?\s*(£[\d,]+(?:\.\d+)?)",
        r"Guide(?:\s*[:*])?\s*(£[\d,]+(?:\.\d+)?)",
        r"Available At\s*(£[\d,]+(?:\.\d+)?)",
    ]:
        m = re.search(pat, text or "", re.I)
        if m:
            return parse_money(m.group(1))
    return None

def parse_rent(text):
    values = []
    for pat in [
        r"(?:Producing|Currently Producing|Current Gross Income|Current Rent Reserved|"
        r"Rent(?:al)?(?: Income)?|Investment Let at|Let at|income of|generating|let producing)"
        r"\s*:?\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
        r"(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b",
    ]:
        for m in re.finditer(pat, text or "", re.I):
            value = parse_money(m.group(1))
            if value and 500 <= value <= 5_000_000:
                values.append(value)
    return max(values) if values else None

def is_commercial(text):
    t = norm(text).lower()
    has_com = any(x in t for x in COMMERCIAL_TERMS)
    has_res = any(x in t for x in RESIDENTIAL_ONLY)
    if has_res and not any(x in t for x in MIXED_MARKERS):
        return False
    return has_com

def parse_tenure(text):
    t = (text or "").lower()
    if "virtual freehold" in t:
        return "Virtual Freehold"
    if "freehold" in t:
        return "Freehold"
    if "leasehold" in t:
        return "Leasehold"
    return None

def parse_vat(text):
    t = (text or "").lower()
    if any(x in t for x in ["vat is not applicable","vat-free","vat free","no vat"]):
        return "NOT APPLICABLE"
    if any(x in t for x in ["vat applicable","vat is applicable","elected to charge vat"]):
        return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def absolutise(base, href):
    return urljoin(base, href or "")
