import pytest
from scripts.verify_live_platform import verify
from web_platform.board import enrich_board_row,index_row
from web_platform.catalogue import identity

class Response:
 def __init__(self,payload=None,text=''):self.payload=payload;self.text=text
 def raise_for_status(self):pass
 def json(self):return self.payload

def test_same_ids_and_collection_date_cannot_mask_stale_financial_facts(monkeypatch):
 raw={'source':'Example','address':'1 High Street AB1 2CD','url':'https://example.org/lot/1','auction_date':'2099-01-01','property_type':'Retail','description':'A vacant commercial shop','guide_price':100000,'annual_rent':None}
 row=enrich_board_row(dict(raw));row['id']=identity(raw)
 indexed=index_row(row,'1.json')
 snapshot={'properties':[raw],'generated_at':'2026-10-05'}
 def fetch(url,**kw):
  if url.endswith('/'):return Response(text='<div data-index="/board/index.json"></div>')
  return Response({'generated_at':snapshot['generated_at'],'rows':[indexed]})
 monkeypatch.setattr('scripts.verify_live_platform.requests.get',fetch)
 assert verify('https://example.org',snapshot)['facts_verified']
 indexed['giy']=10
 with pytest.raises(ValueError,match='facts do not match'):verify('https://example.org',snapshot)
