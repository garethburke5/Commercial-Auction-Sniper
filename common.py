from bs4 import BeautifulSoup
from base import Lot
from parser_utils import *

class NotCommercial(Exception): pass

def detail_lot(auctioneer,url,seed_text="",lot_number=None,force_commercial=False,property_type=None):
    soup=BeautifulSoup(fetch(url),"lxml")
    h1=soup.find("h1"); title=soup.find("title")
    address=norm(h1.get_text(" ",strip=True)) if h1 else (norm(title.get_text(" ",strip=True)).split("|")[0] if title else url)
    main=soup.find("main") or soup.find("article")
    exact=norm(main.get_text(" ",strip=True)) if main else norm(soup.get_text(" ",strip=True))
    if not force_commercial and not strong_commercial(address+" "+exact[:10000]):
        raise NotCommercial(address)
    guide=parse_guide(exact) or parse_guide(seed_text)
    legal_url,legal_status=find_legal_pack(soup,url)
    return Lot(auctioneer=auctioneer,source_url=url,address=address,image_url=find_image(soup,url),postcode=parse_postcode(address),property_type=property_type,lot_number=lot_number,guide_price=guide,annual_rent=parse_rent(exact),tenure=parse_tenure(exact),vat_status=parse_vat(exact),togc_status=parse_togc(exact),legal_pack_status=legal_status,legal_pack_url=legal_url).finalise()
