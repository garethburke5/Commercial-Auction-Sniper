from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.[^"]+"','BUILD = "V6.61-DEEP-EVIDENCE"',s,count=1)

# Imports for legal-pack PDF text extraction.
s=s.replace('import base64\n','import base64\nfrom io import BytesIO\n',1)
s=s.replace('from bs4 import BeautifulSoup\n','from bs4 import BeautifulSoup\ntry:\n    from pypdf import PdfReader\nexcept Exception:\n    PdfReader=None\n',1)

anchor='''# ---------------- UI ----------------\nst.markdown("""'''
helper=r'''
# ---------------- DEEP EVIDENCE / SEMANTIC NORMALISATION ----------------
def _money_mentions(text):
    out=[]
    for m in re.finditer(r"£\s*([\d,]+(?:\.\d+)?)",text or "",re.I):
        try:
            v=float(m.group(1).replace(',',''))
            if 250 <= v <= 10_000_000:
                out.append((v,m.start(),m.end()))
        except Exception:
            pass
    return out


def _classify_rental_evidence(text):
    """Separate current passing rent from historic rent, ERV and asking/proposed rents."""
    text=norm(text or '')
    evidence={"current":[],"historical":[],"erv":[],"other":[]}
    hist_words=r"previous(?:ly)?|former(?:ly)?|historic(?:al|ally)?|last\s+let|was\s+let|had\s+been\s+let|prior\s+rent"
    erv_words=r"\bERV\b|estimated\s+rental\s+value|market\s+rent|asking\s+rent|quoting\s+rent|proposed\s+rent|regear\s+rent|new\s+rent|rising\s+to|reviewed\s+to"
    current_words=r"passing\s+rent|currently\s+let|fully\s+let|let\s+to|producing|rental\s+income|current\s+rent|income\s+of|rent\s+receivable|annual\s+rent"
    for value,start,end in _money_mentions(text):
        left=max(0,start-150); right=min(len(text),end+150)
        ctx=text[left:right]
        if re.search(hist_words,ctx,re.I): kind='historical'
        elif re.search(erv_words,ctx,re.I): kind='erv'
        elif re.search(current_words,ctx,re.I) and not re.search(r"under\s+offer|subject\s+to\s+contract",ctx,re.I): kind='current'
        else: kind='other'
        evidence[kind].append({"value":value,"context":ctx[:300]})
    return evidence


def _normalise_rent_semantics(row):
    r=dict(row)
    text=norm(' '.join(str(r.get(k) or '') for k in ('desc','legal_text','summary','notes')))
    ev=_classify_rental_evidence(text)
    old=r.get('rent')
    current_vals=[x['value'] for x in ev['current']]
    hist_vals=[x['value'] for x in ev['historical']]
    erv_vals=[x['value'] for x in ev['erv']]
    if current_vals:
        current=min(current_vals,key=lambda v:abs(v-float(old))) if old else max(current_vals)
        r['rent']=current
        r['rent_status']='CURRENT / PASSING'
        r['rent_evidence']=next((x['context'] for x in ev['current'] if x['value']==current),'')
    else:
        old_is_historic=bool(old and any(abs(x['value']-float(old)) < 1 for x in ev['historical']))
        old_is_erv=bool(old and any(abs(x['value']-float(old)) < 1 for x in ev['erv']))
        vacancy=bool(re.search(r"vacant(?:\s+possession)?|currently\s+vacant|former\s+tenant|lease\s+expired",text,re.I))
        if old_is_historic or old_is_erv or (vacancy and not re.search(r"part(?:ly)?\s+let|income\s+producing",text,re.I)):
            r['rent']=None
            r['rent_status']='NO CONFIRMED CURRENT RENT'
            r['rent_evidence']='Historical/ERV evidence was found, but no explicit current passing rent was confirmed.'
        elif old:
            r['rent_status']='COLLECTOR VALUE — VERIFY'
            r['rent_evidence']='Collector supplied a rent figure, but the captured text does not yet positively identify it as current passing rent.'
    if hist_vals:
        r['previous_rent']=hist_vals[0]
        r['previous_rent_evidence']=ev['historical'][0]['context']
    if erv_vals:
        r['erv']=erv_vals[0]
        r['erv_evidence']=ev['erv'][0]['context']
    r['yield']=100*float(r['rent'])/float(r['guide']) if r.get('guide') and r.get('rent') else None
    return r


def _legal_links(page_url,soup):
    scored=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(page_url,a.get('href')).split('#')[0]
        label=norm(a.get_text(' ',strip=True)+' '+href).lower()
        score=0
        if 'legal pack' in label: score+=10
        if 'special condition' in label: score+=8
        if re.search(r'\blease\b|tenancy|occupational lease',label): score+=6
        if 'epc' in label or 'energy performance' in label: score+=7
        if href.lower().split('?')[0].endswith('.pdf'): score+=4
        if score and href.startswith('http'): scored.append((score,href))
    out=[]
    for _score,u in sorted(scored,key=lambda x:-x[0]):
        if u not in out: out.append(u)
    return out[:8]


def _pdf_text(url,referer=None,max_pages=25):
    if PdfReader is None: return ''
    try:
        h=dict(HEADERS)
        if referer: h['Referer']=referer
        resp=requests.get(url,headers=h,timeout=16,allow_redirects=True)
        ct=(resp.headers.get('content-type') or '').lower()
        if not resp.ok or ('pdf' not in ct and not url.lower().split('?')[0].endswith('.pdf')) or len(resp.content)>10_000_000:
            return ''
        reader=PdfReader(BytesIO(resp.content))
        chunks=[]
        for page in reader.pages[:max_pages]:
            try:
                t=page.extract_text() or ''
                if t: chunks.append(t)
            except Exception: pass
            if sum(map(len,chunks))>30000: break
        return norm(' '.join(chunks))[:30000]
    except Exception:
        return ''


@st.cache_data(ttl=21600,show_spinner=False)
def _deep_page_evidence(url):
    if not url: return {"page_text":"","legal_text":"","legal_links":[]}
    try:
        raw=fetch(url); soup=BeautifulSoup(raw,'lxml')
        main=soup.find('main') or soup
        for tag in main.find_all(['script','style','nav','footer','header']): tag.decompose()
        page_text=norm(main.get_text(' ',strip=True))[:18000]
        links=_legal_links(url,soup)
        legal=[]
        for link in links[:3]:
            if link.lower().split('?')[0].endswith('.pdf'):
                t=_pdf_text(link,url)
                if t: legal.append(t)
        return {"page_text":page_text,"legal_text":norm(' '.join(legal))[:40000],"legal_links":links}
    except Exception:
        return {"page_text":"","legal_text":"","legal_links":[]}


def _deep_enrich_rows(rows,limit=70):
    rows=[dict(x) for x in rows]
    idx=[]
    for i,r in enumerate(rows):
        u=r.get('url') or ''
        if not u: continue
        txt=(str(r.get('desc') or '')).lower()
        score=(5 if r.get('rent') else 0)+(3 if 'legal' in txt else 0)+(2 if not r.get('epc') and not r.get('epc_rating') else 0)
        idx.append((score,i))
    idx=[i for _s,i in sorted(idx,reverse=True)[:limit]]
    def one(i):
        r=rows[i]; ev=_deep_page_evidence(r.get('url'))
        if ev.get('page_text'): r['desc']=norm((r.get('desc') or '')+' '+ev['page_text'])[:22000]
        if ev.get('legal_text'): r['legal_text']=ev['legal_text']
        if ev.get('legal_links'):
            r['legal_links']=ev['legal_links']; r['legal_pack_url']=ev['legal_links'][0]
        return i,_normalise_rent_semantics(r)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs=[ex.submit(one,i) for i in idx]
        for f in as_completed(futs):
            try:
                i,r=f.result(); rows[i]=r
            except Exception: pass
    return [_normalise_rent_semantics(r) for r in rows]

'''
if anchor not in s: raise SystemExit('UI anchor missing')
s=s.replace(anchor,helper+anchor,1)
needle='''    refreshed=_enrich_missing_images(refreshed,limit=220)\n\n    # Non-shrink guard'''
replace='''    refreshed=_enrich_missing_images(refreshed,limit=220)\n    refreshed=_deep_enrich_rows(refreshed,limit=70)\n\n    # Non-shrink guard'''
if needle not in s: raise SystemExit('refresh enrichment anchor missing')
s=s.replace(needle,replace,1)
needle='''    rows=_v657_localise_priority_rows(rows)\nexcept Exception:\n    pass\nst.markdown('''
replace='''    rows=_v657_localise_priority_rows(rows)\n    rows=[_normalise_rent_semantics(r) for r in rows]\nexcept Exception:\n    pass\nst.markdown('''
if needle not in s: raise SystemExit('boot rows anchor missing')
s=s.replace(needle,replace,1)
old='''        p.get("vat"),\n    ]'''
new='''        p.get("vat"),\n        p.get("legal_text"),\n        p.get("rent_evidence"),\n        p.get("previous_rent_evidence"),\n        p.get("erv_evidence"),\n    ]'''
if old in s: s=s.replace(old,new,1)
needle='''    if tenant: f["Tenant"]=tenant\n    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'\n'''
replace='''    if tenant: f["Tenant"]=tenant\n    if p.get("rent"): f["Passing rent"]=f'£{p["rent"]:,.0f} p.a.'\n    if p.get("rent_status"): f["Rent status"]=p["rent_status"]\n    if p.get("previous_rent"):\n        f["Previous / historic rent"]=f'£{p["previous_rent"]:,.0f} p.a. — NOT current income'\n        chips.append("HISTORIC RENT")\n    if p.get("erv"):\n        f["ERV / market-rent evidence"]=f'£{p["erv"]:,.0f} p.a. — NOT passing rent'\n        chips.append("ERV")\n    if p.get("legal_text"):\n        f["Legal documents scanned"]="Yes — extracted text used in analysis"\n        chips.append("LEGAL TEXT SCANNED")\n    elif p.get("legal_pack_url"):\n        f["Legal pack"]="Link found — text not yet extractable"\n'''
if needle not in s: raise SystemExit('investment rent anchor missing')
s=s.replace(needle,replace,1)
old='''    return ('<div class="research">'\n            f'<a target="_blank" href="https://www.google.com/search?q={qh}">Sales / auction history ↗</a>'\n'''
new='''    legal=(f'<a target="_blank" href="{html.escape(str(p.get("legal_pack_url")),quote=True)}">Legal pack / document ↗</a>' if p.get("legal_pack_url") else "")\n    return ('<div class="research">'+legal\n            +f'<a target="_blank" href="https://www.google.com/search?q={qh}">Sales / auction history ↗</a>'\n'''
if old not in s: raise SystemExit('research link anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.61 deep evidence extraction and semantic rent classification applied')
# deployment trigger
