from bs4 import BeautifulSoup
from base import Lot
from parser_utils import fetch,norm,parse_guide,parse_rent,parse_postcode,parse_tenure,parse_vat,parse_togc,find_image,find_legal_pack,strong_commercial

class NotCommercial(Exception):pass

def detail_lot(auctioneer,url,seed_text="",lot_number=None,auction_date=None,sess=None,force_commercial=False,property_type=None):
    soup=BeautifulSoup(fetch(url,sess=sess),"lxml")
    h1=soup.find("h1"); title=soup.find("title")
    address=norm(h1.get_text(" ",strip=True)) if h1 else (norm(title.get_text(" ",strip=True)).split("|")[0] if title else url)
    main=soup.find("main") or soup.find("article")
    body=norm(main.get_text(" ",strip=True)) if main else norm(soup.get_text(" ",strip=True))
    exact=norm(address+" "+body[:10000])
    if not force_commercial:
        ok,reason=strong_commercial(exact)
        if not ok:raise NotCommercial(reason)
        property_type=property_type or reason
    guide=parse_guide(exact)
    if guide is None: guide=parse_guide(seed_text)
    rent=parse_rent(exact)
    legal_url,legal_status=find_legal_pack(soup,url)
    return Lot(auctioneer=auctioneer,source_url=url,address=address,image_url=find_image(soup,url),postcode=parse_postcode(address),property_type=property_type,auction_date=auction_date,lot_number=lot_number,guide_price=guide,annual_rent=rent,tenure=parse_tenure(exact),vat_status=parse_vat(exact),togc_status=parse_togc(exact),legal_pack_status=legal_status,legal_pack_url=legal_url).finalise()
