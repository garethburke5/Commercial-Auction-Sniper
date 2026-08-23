from bs4 import BeautifulSoup
from base import Lot
from parser_utils import *
class NotCommercial(Exception):pass
def detail_lot(auctioneer,url,seed_text="",lot_number=None,session=None,force_commercial=False):
    s=BeautifulSoup(fetch(url,session=session),"lxml")
    h1=s.find("h1");title=s.find("title")
    address=norm(h1.get_text(" ",strip=True)) if h1 else (norm(title.get_text(" ",strip=True)).split("|")[0] if title else url)
    main=s.find("main") or s.find("article")
    body=norm(main.get_text(" ",strip=True)) if main else norm(s.get_text(" ",strip=True))
    evidence=norm(address+" "+seed_text+" "+body[:6000])
    ok,why=commercial_evidence(evidence)
    if not force_commercial and not ok:raise NotCommercial(why)
    legal_url,legal_status=find_legal_pack(s,url)
    return Lot(
      auctioneer=auctioneer,source_url=url,address=address,image_url=find_image(s),
      postcode=parse_postcode(evidence),property_type=why,lot_number=lot_number,
      guide_price=parse_guide(evidence),annual_rent=parse_rent(evidence),
      tenure=parse_tenure(evidence),vat_status=parse_vat(evidence),togc_status=parse_togc(evidence),
      legal_pack_status=legal_status,legal_pack_url=legal_url
    ).finalise()
