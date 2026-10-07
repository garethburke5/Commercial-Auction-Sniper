"""Read certificate evidence and match street/unit identity, never postcode alone."""
import re
from datetime import datetime
from acquisition_evidence_graph import norm

MONTH=r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'

def identifiers(text):
    text=norm(text).lower().replace('–','-').replace('—','-')
    text=re.sub(r'\bst\b','street',text);text=re.sub(r'\brd\b','road',text)
    text=re.sub(r'[,()]',' ',text);text=norm(text)
    return set(re.findall(r'\b\d+[a-z]?(?:\s*-\s*\d+[a-z]?)?\s+(?:(?:the|[a-z]+)\s+){0,3}(?:street|road|lane|avenue|arcade|way|gardens)\b',text))

def pack_certificates(model,demises):
    records=[]
    docs={d['document']:d for d in model.get('documents',[]) if d.get('type')=='epc'}
    for name,document in docs.items():
        pages=[p for p in model.get('source_pages',[]) if p['document']==name]
        text=norm(' '.join(p.get('text','') for p in pages[:2]))
        rating=re.search(r'(?:current )?energy rating is\s*([A-G])\b',text,re.I)
        expiry=re.search(r'Valid until\s*:?\s*(\d{1,2}\s+'+MONTH+r'\s+20\d{2})',text,re.I)
        number=re.search(r'\b\d{4}-\s*\d{4}-\s*\d{4}-\s*\d{4}-\s*\d{4}\b',text)
        area=re.search(r'Total floor area\s*(\d+(?:\.\d+)?)\s*square metres',text,re.I)
        if not rating or not expiry:continue
        address_ids=identifiers(text[:700])
        if not address_ids:continue
        units=set(re.findall(r'\bunit\s+(\d+[a-z]?)\b',text[:700],re.I))
        for demise in demises:
            if demise['residential_reversion']:continue
            front=norm(' '.join(p.get('text','') for p in model.get('source_pages',[]) if p['document']==demise.get('document') and (p.get('page') or 0)<=8))
            address_contexts=re.findall(r'(?:relating to|known as|situate at|LR4\.?\s*Property)\s*.{0,260}',front,re.I)
            candidates=identifiers(' '.join(address_contexts))
            if not address_ids.intersection(candidates):continue
            if units and not units <= set(re.findall(r'\bunit\s+(\d+[a-z]?)\b',front,re.I)):continue
            p=pages[0]
            records.append({'kind':'epc_certificate','subject':', '.join(sorted(address_ids)), 'demise_document':demise['document'],
                'rating':rating[1].upper(),'valid_until':datetime.strptime(expiry[1],'%d %B %Y').date().isoformat(),
                'certificate_number':re.sub(r'\s+','',number[0]) if number else None,'floor_area_sqm':float(area[1]) if area else None,
                'address':', '.join(sorted(address_ids)), 'quote':text[:1000],
                'scope_note':'Supplied certificate matched by street/unit identity, not postcode or occupier name. Confirm physical extent and whether a newer assessment supersedes it.',
                'pack_evidence':{'document':name,'page':p.get('page'),'document_sha256':document['sha256'],'excerpt':p.get('text','')},
                'source':{'title':name,'text':p.get('text','')}})
    return records
