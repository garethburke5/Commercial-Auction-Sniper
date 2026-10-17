"""Conservative, sourced registered-owner intelligence for property pages.

Registered proprietors are not assumed to be contractual auction sellers.
No Companies House financial information or motive is inferred from a title.
Only manually corroborated, dated title evidence enters the public fixture.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).parent
_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _address_tokens(value):
    return " ".join(_NON_WORD.sub(" ", str(value or "").lower()).split())


def _postcode(value):
    found = _POSTCODE.search(str(value or ""))
    return (found.group(1) + found.group(2)).upper() if found else None


def _same_property(row, record):
    """Require exact postcode AND street-number/name, not a fuzzy name match."""
    address = str(row.get("address") or "")
    if _postcode(address) != _postcode(record.get("address")):
        return False
    target = _address_tokens(record["street"])
    actual = _address_tokens(address)
    # Allow '22 The Broadway' vs '22 Broadway', without matching 122 Broadway.
    if target == "22 broadway":
        return bool(re.search(r"\b22 (?:the )?broadway\b", actual))
    return bool(re.search(r"(?<!\w)" + re.escape(target) + r"(?!\w)", actual))


class OwnerRegistry:
    """Small, explicit evidence registry: no costly background title requests."""
    def __init__(self, records=()):
        self.records = list(records)

    @classmethod
    def from_file(cls, path=None):
        source = Path(path) if path is not None else HERE / "owner_evidence.json"
        if not source.exists():
            return cls()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("Unsupported registered-owner evidence schema")
        return cls(payload.get("properties", []))

    def match(self, row):
        matches = [r for r in self.records if _same_property(row, r)]
        # Ambiguous title matches must not be silently presented as confirmed.
        return matches[0] if len(matches) == 1 else None

    def index(self, rows):
        """Build links to actual captured appearances; do not invent listing URLs."""
        result = {}
        for row in rows:
            match = self.match(row)
            if not match:
                continue
            key = match["title_number"]
            if key not in result or str(row.get("auction_date") or "") > str(result[key].get("auction_date") or ""):
                result[key] = row
        return result

    def context(self, row, captured_by_title=None):
        record = self.match(row)
        if not record:
            return None
        company = record["company"]
        siblings = []
        for other in self.records:
            if other["title_number"] == record["title_number"] or other["company"]["number"] != company["number"]:
                continue
            captured = (captured_by_title or {}).get(other["title_number"])
            siblings.append({
                "address": other["address"],
                "title_number": other["title_number"],
                "verified_as_of": other["verified_as_of"],
                "path": captured.get("path") if captured else None,
                "caption": "Other registered holding; contractual seller not confirmed",
            })
        guide = row.get("guide_price")
        acquisition = record.get("recorded_purchase_price")
        return {
            "company_name": company["name"],
            "company_number": company["number"],
            "company_url": "https://find-and-update.company-information.service.gov.uk/company/" + company["number"],
            "title_number": record["title_number"],
            "verified_as_of": record["verified_as_of"],
            "source_description": record["evidence"],
            "recorded_purchase_price": acquisition,
            "guide_comparison_available": isinstance(guide, (int, float)) and guide > 0 and isinstance(acquisition, (int, float)),
            "related": siblings,
            "seller_status": "Contractual auction seller not established by the title alone",
            "motivation_status": "Sale motivation not independently established; portfolio rotation or raising capital are hypotheses, not findings.",
            "filings_status": "Company accounts, charges and directors are not automatically verified by this title evidence.",
        }
