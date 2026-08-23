from bs4 import BeautifulSoup
from base import Lot
from parser_utils import (
    fetch,normalise_space,parse_guide,parse_rent,parse_postcode,
    parse_tenure,parse_vat,parse_togc,find_image,find_legal_pack,
    property_evidence_text,classify_commercial
)

class NotCommercial(Exception):
    pass

def detail_lot(auctioneer,url,seed_text="",lot_number=None,auction_date=None,property_type=None,session=None):
    soup=BeautifulSoup(fetch(url,session=session),"lxml")
    text=normalise_space(soup.get_text(" ",strip=True))

    evidence=property_evidence_text(soup)
    is_commercial,reason=classify_commercial(evidence)
    if not is_commercial:
        raise NotCommercial(reason)

    h1=soup.find("h1")
    address=normalise_space(h1.get_text(" ",strip=True)) if h1 else None
    if not address:
        title=soup.find("title")
        address=normalise_space(title.get_text(" ",strip=True)).split("|")[0] if title else url

    guide=parse_guide(evidence) or parse_guide(seed_text) or parse_guide(text)
    rent=parse_rent(evidence) or parse_rent(seed_text) or parse_rent(text)
    legal_url,legal_status=find_legal_pack(soup,url)

    status="Live";low=evidence.lower()
    if "sold prior" in low:status="Sold Prior"
    elif "withdrawn" in low:status="Withdrawn"
    elif "postponed" in low:status="Postponed"

    return Lot(
        auctioneer=auctioneer,source_url=url,address=address,
        image_url=find_image(soup),
        postcode=parse_postcode(address+" "+evidence[:1500]),
        property_type=reason,
        auction_date=auction_date,lot_number=lot_number,status=status,
        guide_price=guide,annual_rent=rent,tenure=parse_tenure(evidence),
        vat_status=parse_vat(evidence),togc_status=parse_togc(evidence),
        legal_pack_status=legal_status,legal_pack_url=legal_url
    ).finalise()
