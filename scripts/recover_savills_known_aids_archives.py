#!/usr/bin/env python3
import json,re,requests
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import quote
from datetime import datetime,timezone

OUT=Path("data/savills_raw_lots.json")
STATUS=Path("data/savills_raw_harvest_status.json")
AIDS=[1080,1032,993]
UA={"User-Agent":"Mozilla/5.0 CommercialAuctionSniper/2.0"}

def fetch(session,url):
    attempts=[]
    try:
        r=session.get(url,headers=UA,timeout=12)
        attempts.append({"route":"live","status":r.status_code})
        if r.status_code==200 and len(r.text)>500:return r.text,url,"live",attempts
    except Exception as e: attempts.append({"route":"live","error":str(e)[:160]})
    try:
        cdx="https://web.archive.org/cdx/search/cdx?url="+quote(url,safe="")+"&output=json&filter=statuscode:200&collapse=digest&fl=timestamp&from=2010&to=2018"
        r=session.get(cdx,headers=UA,timeout=15); data=r.json() if r.status_code==200 else []
        attempts.append({"route":"wayback_cdx","status":r.status_code,"captures":max(0,len(data)-1) if isinstance(data,list) else 0})
        for row in reversed(data[1:] if isinstance(data,list) else []):
            snap=f"https://web.archive.org/web/{row[0]}id_/{url}"
            try:
                s=session.get(snap,headers=UA,timeout=15)
                if s.status_code==200 and len(s.text)>500:return s.text,snap,"wayback",attempts
            except Exception: pass
    except Exception as e: attempts.append({"route":"wayback_cdx","error":str(e)[:160]})
    try:
        indexes=session.get("https://index.commoncrawl.org/collinfo.json",headers=UA,timeout=15).json()
        for idx in indexes:
            api=idx.get("cdx-api")
            if not api: continue
            try:
                q=session.get(api,params={"url":url,"output":"json"},headers=UA,timeout=10)
                if q.status_code!=200: continue
                for line in q.text.splitlines():
                    try: rec=json.loads(line)
                    except Exception: continue
                    ts=str(rec.get("timestamp",""))
                    if not ("2010"<=ts[:4]<="2018"):continue
                    off,ln,fn=rec.get("offset"),rec.get("length"),rec.get("filename")
                    if off is None or ln is None or not fn:continue
                    w=session.get("https://data.commoncrawl.org/"+fn,headers={**UA,"Range":f"bytes={off}-{int(off)+int(ln)-1}"},timeout=20)
                    if w.status_code not in (200,206):continue
                    raw=w.content
                    # Search the WARC payload directly; BeautifulSoup tolerates headers.
                    txt=raw.decode("utf-8","ignore")
                    if "Savills" in txt and len(txt)>500:return txt,api,"commoncrawl",attempts
            except Exception: continue
        attempts.append({"route":"commoncrawl","status":"no_usable_capture"})
    except Exception as e: attempts.append({"route":"commoncrawl","error":str(e)[:160]})
    return None,None,None,attempts

def rows_from(html,aid,source,route):
    soup=BeautifulSoup(html,"html.parser"); text=" ".join(soup.stripped_strings)
    if "savills" not in text.lower():return []
    dm=re.search(r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2})",text,re.I)
    date=None
    if dm:
        from datetime import datetime as D
        for fmt in ("%d %B %Y","%d %b %Y"):
            try:date=D.strptime(dm.group(1),fmt).date().isoformat();break
            except ValueError:pass
    out=[]
    for tr in soup.find_all("tr"):
        cells=[" ".join(x.stripped_strings) for x in tr.find_all(["td","th"])]
        joined=" | ".join(x for x in cells if x)
        m=re.search(r"\bLot\s*(\d+[A-Za-z]?)\b",joined,re.I)
        if not m:continue
        lot=m.group(1).upper()
        out.append({"source_event_id":f"SAVILLS-PA-AID{aid}-LOT-{lot}","auctioneer":"Savills","auction_date":date,"source_auction_id":f"AID:{aid}","lot_number":lot,"property_type":None,"location":None,"result":None,"source_url":f"https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}","source_archive_url":source if route!="live" else None,"auction_url":f"https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}","lot_url":None,"source_lot_id":None,"captured_at":datetime.now(timezone.utc).isoformat(),"canonical_property_id":None,"source_visible_text":joined,"retrieval_route":route})
    return out

def main():
    obj=json.loads(OUT.read_text()); lots=obj.get("lots",[])
    keys={(str(x.get("source_auction_id")),str(x.get("lot_number"))) for x in lots}
    s=requests.Session(); blockers=[]; added=0; recovered=[]
    for aid in AIDS:
        url=f"https://www.propertyauctions.com/Results/LotList.aspx?AID={aid}"
        html,src,route,attempts=fetch(s,url)
        if not html:
            blockers.append({"aid":aid,"attempts":attempts});continue
        rows=rows_from(html,aid,src,route)
        if not rows:
            blockers.append({"aid":aid,"route":route,"reason":"retrieved page but no Savills lot rows"});continue
        n=0
        for row in rows:
            k=(row["source_auction_id"],row["lot_number"])
            if k not in keys: lots.append(row);keys.add(k);added+=1;n+=1
        recovered.append({"aid":aid,"route":route,"observable_rows":len(rows),"new_rows":n})
    obj["lots"]=lots;obj["captured_at"]=datetime.now(timezone.utc).isoformat();OUT.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+"\n")
    st=json.loads(STATUS.read_text());st["captured_at"]=datetime.now(timezone.utc).isoformat();st["total_raw_lots"]=len(lots);st["new_or_updated_run"]=added;st["archive_recovery"]=recovered;st["archive_recovery_blockers"]=blockers;STATUS.write_text(json.dumps(st,indent=2)+"\n")
    print("RAW_LOTS",len(lots),"NEW",added,"RECOVERED",recovered,"BLOCKERS",len(blockers))
if __name__=="__main__":main()
