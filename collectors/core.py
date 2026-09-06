from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional
import hashlib
import re
from urllib.parse import urljoin

MONEY_RE = re.compile(r"(?:£\s*)+([\d,]+(?:\.\d{1,2})?)")

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

DESCRIPTION_START_MARKERS = (
    "Property Details Description",
    "Property Description",
)
DESCRIPTION_FALLBACK_START_MARKERS = (
    "Key Features",
    "Key features",
    "Description",
    "Property Information",
    "Property information",
)
DESCRIPTION_END_MARKERS = (
    "Costs Auction Details",
    "Auction Details The sale of this property",
    "Auction Deposit and Fees",
    "Address Open in Google Maps",
    "Open in Google Maps",
    "Our Nearest Office",
    "Sign Up For Auction Alerts",
)
DESCRIPTION_CHROME = re.compile(
    r"(?:book your free appraisal|register to bid|create account\s*/\s*login|my account|"
    r"auction countdown|book a viewing|arrange a viewing|sign up for auction alerts|"
    r"contact our team of auction experts|cancel proxy bid|remove from wishlist|add to wishlist|"
    r"connecting to auction|please wait)",
    re.I,
)
LET_EVIDENCE = re.compile(
    r"\b(?:is|are|unit|shop|flat|property|premises)\s+let\b|\blet\s+to\b|"
    r"\btenancy details\b|\bcurrent (?:gross )?income\b|\bproducing\s+£",
    re.I,
)
VACANT_EVIDENCE = re.compile(r"\bvacant(?: possession)?\b", re.I)


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _first_marker(value, markers, case_sensitive=False):
    haystack = value if case_sensitive else value.lower()
    hits = []
    for marker in markers:
        needle = marker if case_sensitive else marker.lower()
        pos = haystack.find(needle)
        if pos >= 0:
            hits.append((pos, marker))
    return min(hits, default=None, key=lambda x: x[0])


def clean_description(text):
    value = norm(text)
    if not value:
        return ""

    strong = _first_marker(value, DESCRIPTION_START_MARKERS)
    if strong:
        pos, marker = strong
        value = value[pos + len(marker):].strip(" :-|")
    else:
        chrome = DESCRIPTION_CHROME.search(value)
        fallback = _first_marker(value, DESCRIPTION_FALLBACK_START_MARKERS, case_sensitive=True)
        if fallback and (chrome or fallback[0] <= 2500):
            pos, marker = fallback
            value = value[pos + len(marker):].strip(" :-|")

    lowered = value.lower()
    end_positions = []
    for marker in DESCRIPTION_END_MARKERS:
        pos = lowered.find(marker.lower())
        if pos > 0:
            end_positions.append(pos)
    if end_positions:
        value = value[:min(end_positions)].strip(" :-|")

    tail_chrome = DESCRIPTION_CHROME.search(value)
    if tail_chrome and tail_chrome.start() >= 120:
        value = value[:tail_chrome.start()].strip(" :-|")

    value = DESCRIPTION_CHROME.sub(" ", value)
    value = norm(value).strip(" :-|")
    if len(value) > 9000:
        value = value[:9000].rsplit(" ", 1)[0].strip()
    return norm(value)


def normalize_occupation(occupation, description):
    current = norm(occupation)
    if current.lower() not in {"vacant", "vacant possession"} and not current.lower().startswith("vacant -"):
        return current or None
    particulars = clean_description(description)
    if particulars and LET_EVIDENCE.search(particulars):
        if VACANT_EVIDENCE.search(particulars):
            return "Part Vacant / Part Let"
        return "Let"
    return current or None


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
    area_sqft: Optional[float] = None
    area_sqm: Optional[float] = None
    site_area_acres: Optional[float] = None
    tenant: Optional[str] = None
    lease_term: Optional[str] = None
    lease_start: Optional[str] = None
    lease_expiry: Optional[str] = None
    break_clause: Optional[str] = None
    break_status: Optional[str] = None
    rent_review: Optional[str] = None
    fri: Optional[bool] = None
    erv: Optional[float] = None
    epc: Optional[str] = None
    rateable_value: Optional[float] = None
    service_charge: Optional[float] = None
    ground_rent: Optional[float] = None
    property_type: Optional[str] = None
    occupation: Optional[str] = None
    parking: Optional[str] = None
    development_potential: Optional[bool] = None
    asset_management: Optional[bool] = None
    refurbishment: Optional[bool] = None
    residential_conversion: Optional[bool] = None
    listed_status: Optional[str] = None
    covenant_rating: Optional[str] = None
    covenant_risk: Optional[str] = None
    covenant_turnover: Optional[str] = None
    guarantors: Optional[str] = None
    pitch: Optional[str] = None
    nearby_occupiers: Optional[str] = None

    def finalise(self):
        self.description = clean_description(self.description)
        self.occupation = normalize_occupation(self.occupation, self.description)
        occ = (self.occupation or "").strip().lower()
        wholly_vacant = occ in {"vacant", "vacant possession"} or occ.startswith("vacant -")
        if wholly_vacant:
            self.annual_rent = None
            self.gross_yield = None
        elif self.guide_price and self.annual_rent:
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
    expected_count: Optional[int] = None
    discovered_count: Optional[int] = None
    authoritative_snapshot: bool = False
    scope_dates: tuple[str, ...] = ()

    @property
    def coverage_pct(self):
        if not self.expected_count:
            return None
        return round(len(self.lots) / self.expected_count * 100, 1)

    def to_status_dict(self):
        return {
            "source": self.source,
            "status": self.status,
            "lots_seen": len(self.lots),
            "expected_count": self.expected_count,
            "discovered_count": self.discovered_count,
            "coverage_pct": self.coverage_pct,
            "authoritative_snapshot": self.authoritative_snapshot,
            "scope_dates": list(self.scope_dates),
            "message": self.message,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

def parse_money(text):
    m = MONEY_RE.search(str(text or ""))
    return float(m.group(1).replace(",", "")) if m else None

def parse_guide(text):
    money = r"((?:£\s*)+[\d,]+(?:\.\d+)?)"
    # Auctioneers commonly decorate labels as "Guide Price*: £...", "Guide Price: £..."
    # or "Guide**: £...". Keep free whitespace valid too, including duplicated £ markers.
    separator = r"\s*(?:[:*+\-–—|.]\s*)*"
    for pat in [
        rf"Guide Price{separator}{money}",
        rf"Guide{separator}{money}",
        rf"Available At{separator}{money}",
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
    if any(x in t for x in ["elected for vat","elected to charge vat","vat applicable","vat is applicable"]):
        return "APPLICABLE"
    return "MENTIONED - VERIFY" if "vat" in t else "UNKNOWN"

def absolutise(base, href):
    return urljoin(base, href or "")