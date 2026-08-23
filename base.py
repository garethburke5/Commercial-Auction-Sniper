from dataclasses import dataclass, asdict
import hashlib

@dataclass
class Lot:
    auctioneer: str
    source_url: str
    address: str
    image_url: str | None = None
    postcode: str | None = None
    property_type: str | None = None
    auction_date: str | None = None
    lot_number: str | None = None
    status: str = "Live"
    guide_price: float | None = None
    annual_rent: float | None = None
    gross_yield: float | None = None
    tenure: str | None = None
    vat_status: str = "UNKNOWN"
    togc_status: str = "UNKNOWN"
    legal_pack_status: str = "UNKNOWN"
    legal_pack_url: str | None = None
    source_id: str = ""
    confidence: str = "SOURCE_VERIFIED"

    def finalise(self):
        if not self.source_id:
            self.source_id = hashlib.sha1(f"{self.auctioneer}|{self.source_url}".encode()).hexdigest()
        self.gross_yield = round(self.annual_rent / self.guide_price * 100, 2) if self.guide_price and self.annual_rent else None
        return self

    def as_dict(self):
        return asdict(self.finalise())

class CollectorResult:
    def __init__(self, source, status="OK", lots=None, message=""):
        self.source = source
        self.status = status
        self.lots = lots or []
        self.message = message

    def as_dict(self):
        return {"source": self.source, "status": self.status, "lots": len(self.lots), "message": self.message}
