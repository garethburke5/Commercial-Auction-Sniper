"""Resolve published lot context and retrieve only explicit public pack files."""
from pathlib import Path
from urllib.parse import urlsplit,urljoin,unquote
import ipaddress,json,re,socket
import requests

ROOT=Path(__file__).parent
MAX_DOWNLOAD=60*1024*1024

def property_context(property_id):
 if not re.fullmatch(r'[a-f0-9]{20}',str(property_id or '')):return {}
 from web_platform.catalogue import identity
 snapshot=json.loads((ROOT/'data/properties.json').read_text())
 for row in snapshot.get('properties',[])+snapshot.get('archive',[]):
  if identity(row)==property_id:
   return {'id':property_id,'reference':row['address'],'guide':row.get('guide_price'),
    'rent':row.get('annual_rent'),'url':row.get('url'),'legal_pack_url':row.get('legal_pack_url'),
    'source':row.get('source'),'description':row.get('description','')}
 return {}

def is_direct_pack(url):
 p=urlsplit(str(url or ''))
 return p.scheme=='https' and not p.username and p.path.lower().endswith(('.pdf','.zip'))

def _public_address(url):
 p=urlsplit(url)
 if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('Only a public HTTPS document is supported.')
 records=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
 if not records or any(not ipaddress.ip_address(item[4][0]).is_global for item in records):raise ValueError('The document host is not a public address.')
 return p

def fetch_public_pack(context):
 """Use only the published exact-lot PDF/ZIP, without login or terms acceptance."""
 url=context.get('legal_pack_url')
 if not is_direct_pack(url):raise ValueError('This source uses a document portal or has no direct public pack file. Open the source, sign in if required, then upload its ZIP or selected documents.')
 host=_public_address(url).hostname
 for _ in range(4):
  p=_public_address(url)
  if p.hostname!=host:raise ValueError('The download redirects to another service. Please obtain the pack from the source directly.')
  with requests.get(url,stream=True,timeout=(8,25),allow_redirects=False,headers={'User-Agent':'AuctionSniper/2.0 public legal-pack download'}) as response:
   if response.status_code in (301,302,303,307,308):url=urljoin(url,response.headers.get('Location',''));continue
   if response.status_code in (401,403):raise ValueError('The source requires access through its own portal. Open the source and upload the documents you obtain.')
   response.raise_for_status()
   if int(response.headers.get('Content-Length','0') or 0)>MAX_DOWNLOAD:raise ValueError('The source pack exceeds the 60 MB automatic-download limit; download it directly and upload it.')
   chunks=[];size=0
   for chunk in response.iter_content(65536):
    size+=len(chunk)
    if size>MAX_DOWNLOAD:raise ValueError('The source pack exceeds the 60 MB automatic-download limit.')
    chunks.append(chunk)
   data=b''.join(chunks)
   if not data.startswith((b'%PDF-',b'PK\x03\x04')):raise ValueError('The source returned a web/sign-in page rather than PDF or ZIP documents. Please use the source portal.')
   return Path(unquote(p.path)).name,data
 raise ValueError('The source redirected repeatedly; please obtain the pack directly.')
