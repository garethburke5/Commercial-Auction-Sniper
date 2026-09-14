from __future__ import annotations

import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup,Comment

BASE='https://auctions.savills.co.uk'
PAGES=[f'{BASE}/past-auctions/archive/page-{i}' for i in (9,10,11,12)]
DIAG=Path('data/source_diagnostics/savills_archive_card_forensics.json')
PROGRESS=Path('data/historical_backfill_progress.json')
SOURCE='Savills Auctions'
UA='Mozilla/5.0 (compatible; AuctionSniperHistory/1.0)'
DATE_RE=re.compile(r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]+)\s+(20\d{2})\b')
CAT_ID=re.compile(r'(?:layout=catalogue[^>"\']*?id=|id=)(\d+)',re.I)
NUM_CONTEXT=re.compile(r'(?:(?:auction|commission|catalogue|archive|result|sale|thumbnail)[^0-9]{0,30})(\d{1,6})',re.I)

def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()
def now():return datetime.now(timezone.utc).isoformat()

def fetch(u):
 r=requests.get(u,headers={'User-Agent':UA},timeout=(7,40));r.raise_for_status();return r.text

def parse_card(row,page):
 raw=str(row);text=norm(row.get_text(' '));m=DATE_RE.search(text);date=' '.join(m.groups()) if m else None
 hrefs=[urljoin(BASE,a.get('href')) for a in row.find_all('a',href=True)]
 imgs=[]
 for tag in row.find_all(True):
  for k,v in tag.attrs.items():
   if k in ('src','style','data-src','data-background','data-image'):
    sv=' '.join(v) if isinstance(v,list) else str(v)
    if 'image' in sv.lower() or 'thumbnail' in sv.lower() or '/assets/' in sv.lower():imgs.append(sv)
 comments=[norm(c) for c in row.find_all(string=lambda x:isinstance(x,Comment))]
 attrs=[]
 for tag in row.find_all(True):
  d={k:v for k,v in tag.attrs.items() if k.startswith('data-') or k in ('id','class','v-if','v-for',':href','v-bind:href','onclick')}
  if d:attrs.append({'tag':tag.name,'attrs':d})
 ids=sorted(set(int(x) for x in CAT_ID.findall(raw)))
 nums=sorted(set(int(x) for x in NUM_CONTEXT.findall(raw)))
 return {'page':page,'date':date,'text':text,'hrefs':hrefs,'images':imgs,'comments':comments,'catalogue_ids':ids,'numeric_context_tokens':nums,'attrs':attrs,'raw_html':raw}

def main():
 cards=[];page_meta=[]
 for u in PAGES:
  text=fetch(u);soup=BeautifulSoup(text,'html.parser');rows=soup.select('.archive-calendar__row')
  p=int(u.rsplit('-',1)[-1]);page_meta.append({'page':p,'rows':len(rows),'bytes':len(text)})
  for r in rows:cards.append(parse_card(r,p))
 # Keep 2017-2020 around transition, with exact neighboring card order.
 focus=[c for c in cards if c.get('date') and any(y in c['date'] for y in ('2017','2018','2019','2020'))]
 # Infer visible catalogue IDs from hrefs too.
 for c in focus:
  hrefids=[]
  for h in c['hrefs']:
   m=re.search(r'/auctions/[^/]*-(\d+)(?:$|[/?#])',h)
   if m:hrefids.append(int(m.group(1)))
   m2=re.search(r'[?&]id=(\d+)',h)
   if m2:hrefids.append(int(m2.group(1)))
  c['href_catalogue_ids']=sorted(set(hrefids))
 summary=[]
 for c in focus:
  summary.append({'date':c['date'],'page':c['page'],'href_catalogue_ids':c['href_catalogue_ids'],'catalogue_ids_in_raw':c['catalogue_ids'],'numeric_context_tokens':c['numeric_context_tokens'],'hrefs':c['hrefs'],'images':c['images'],'comments':c['comments']})
 diag={'at':now(),'route':'savills-archive-card-transition-forensics-2017-2020','pages':page_meta,'cards_total':len(cards),'focus_cards':len(focus),'card_summary':summary,'focus_cards_full':focus}
 DIAG.parent.mkdir(parents=True,exist_ok=True);DIAG.write_text(json.dumps(diag,indent=2,ensure_ascii=False),encoding='utf-8')
 p=json.loads(PROGRESS.read_text());s=p.setdefault('sources',{}).setdefault(SOURCE,{})
 s['historically_complete']=False;s['discovery_exhausted']=False;s['last_discovery_mode']=diag['route'];s['savills_archive_card_forensics_last_run']={'at':diag['at'],'route':diag['route'],'cards_total':len(cards),'focus_cards':len(focus),'summary':summary}
 s['savills_archive_card_forensics_last_blocker']={'at':diag['at'],'route':diag['route'],'failing_url_or_route':'Live Savills archive card markup around 2017-2020 platform transition','message':'Compared raw card markup, href IDs, thumbnail/image names, comments and hidden attributes across linked 2019-2020 cards and unlinked 2018/2017 cards.','next_safe_route':'Use any deterministic ID/image/comment relationship found to reconstruct 2018 catalogue URLs. If IDs are absent from cards, enumerate first-party catalogue IDs adjacent to known December-2019 ID=3 through archived/live route variants and validate by exact auction date/lot count before ingestion.'}
 p['updated_at']=diag['at'];PROGRESS.write_text(json.dumps(p,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps({'cards_total':len(cards),'focus_cards':len(focus),'summary':summary},indent=2))

if __name__=='__main__':main()
