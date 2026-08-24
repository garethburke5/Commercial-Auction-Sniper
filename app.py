import re
import html
import sqlite3
from pathlib import Path
from urllib.parse import urljoin

import requests
import streamlit as st
from bs4 import BeautifulSoup

st.set_page_config(page_title='Auction Sniper', page_icon='🎯', layout='wide', initial_sidebar_state='collapsed')

DB = Path('auction_sniper_single.db')
HEADERS = {'User-Agent': 'Mozilla/5.0 CommercialAuctionSniper/3.0'}
TIMEOUT = 25
MONEY_RE = re.compile(r'£\s*([\d,]+(?:\.\d{1,2})?)')

COMMERCIAL_TERMS = [
    'commercial property','commercial unit','commercial building','commercial investment',
    'retail property','retail unit','retail investment','retail building',
    'shop investment','shop and flat','shop with flat','ground floor shop',
    'office property','office building','office investment','office premises',
    'industrial unit','industrial property','industrial investment','warehouse',
    'workshop','factory','trade counter','business premises','business unit',
    'restaurant','takeaway','public house','pub investment','hotel','care home',
    'day nursery','supermarket','pharmacy','showroom','commercial depot',
    'mixed use','mixed-use','commercial and residential','retail and residential',
    'shopping centre','retail park','leisure investment'
]
RESIDENTIAL_TERMS = [
    'residential flat','apartment','maisonette','bungalow','detached house',
    'semi-detached house','terraced house','end of terrace house','family home',
    'dwelling house','retirement flat','studio flat','residential investment'
]


def connect():
    return sqlite3.connect(DB)


def init_db():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS lots(
            source_id TEXT PRIMARY KEY, auctioneer TEXT, source_url TEXT, address TEXT,
            image_url TEXT, lot_number TEXT, guide_price REAL, annual_rent REAL,
            gross_yield REAL, tenure TEXT, vat_status TEXT, legal_pack_status TEXT,
            legal_pack_url TEXT
        );
        CREATE TABLE IF NOT EXISTS source_status(
            source TEXT PRIMARY KEY, status TEXT, lots_seen INTEGER, message TEXT
        );
        ''')


def replace_snapshot(results):
    with connect() as con:
        con.execute('DELETE FROM lots')
        con.execute('DELETE FROM source_status')
        for source, status, lots, message in results:
            con.execute('INSERT OR REPLACE INTO source_status VALUES (?,?,?,?)',
                        (source, status, len(lots), message))
            for x in lots:
                con.execute('''INSERT OR REPLACE INTO lots VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (x['source_id'], x['auctioneer'], x['source_url'], x['address'],
                     x.get('image_url'), x.get('lot_number'), x.get('guide_price'),
                     x.get('annual_rent'), x.get('gross_yield'), x.get('tenure'),
                     x.get('vat_status','UNKNOWN'), x.get('legal_pack_status','NOT FOUND'),
                     x.get('legal_pack_url')))


def get_lots(max_price, min_yield, include_unknown):
    clauses = ['(guide_price IS NULL OR guide_price <= ?)']
    params = [max_price]
    clauses.append('(gross_yield IS NULL OR gross_yield >= ?)' if include_unknown else '(gross_yield IS NOT NULL AND gross_yield >= ?)')
    params.append(min_yield)
    with connect() as con:
        con.row_factory = sqlite3.Row
        q = 'SELECT * FROM lots WHERE ' + ' AND '.join(clauses) + ' ORDER BY CASE WHEN gross_yield IS NULL THEN 1 ELSE 0 END, gross_yield DESC'
        return [dict(r) for r in con.execute(q, params)]


def get_sources():
    with connect() as con:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute('SELECT * FROM source_status ORDER BY source')]


def count_all():
    with connect() as con:
        return int(con.execute('SELECT COUNT(*) FROM lots').fetchone()[0])


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def norm(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def parse_money(v):
    m = MONEY_RE.search(str(v or ''))
    return float(m.group(1).replace(',', '')) if m else None


def parse_guide(text):
    for p in [r'Guide Price\*?\s*:?\s*(£[\d,]+(?:\.\d+)?)', r'Guide\s*:?\s*(£[\d,]+(?:\.\d+)?)', r'Available At\s*:?\s*(£[\d,]+(?:\.\d+)?)']:
        m = re.search(p, text or '', re.I)
        if m:
            return parse_money(m.group(1))
    return None


def parse_rent(text):
    vals = []
    patterns = [
        r'(?:Producing|Current Rent Reserved|Rent(?:al)?(?: Income)?|Investment Let at|Let at|income of|generating)\s*(?:approximately\s*)?(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b',
        r'(£[\d,]+(?:\.\d+)?)\s*(?:per annum|p\.?a\.?|pa)\b'
    ]
    for p in patterns:
        for m in re.finditer(p, text or '', re.I):
            v = parse_money(m.group(1))
            if v and 500 <= v <= 2_000_000:
                vals.append(v)
    return max(vals) if vals else None


def commercial(text):
    t = norm(text).lower()
    has_commercial = any(term in t for term in COMMERCIAL_TERMS)
    has_residential = any(term in t for term in RESIDENTIAL_TERMS)
    return has_commercial and not (has_residential and not has_commercial)


def parse_tenure(text):
    t = text.lower()
    if 'virtual freehold' in t: return 'Virtual Freehold'
    if 'freehold' in t: return 'Freehold'
    if 'leasehold' in t: return 'Leasehold'
    return None


def parse_vat(text):
    t = text.lower()
    if any(x in t for x in ['no vat','vat is not applicable','vat free']): return 'NOT APPLICABLE'
    if any(x in t for x in ['vat applicable','vat is applicable']): return 'APPLICABLE'
    return 'MENTIONED - VERIFY' if 'vat' in t else 'UNKNOWN'


def image_url(soup, base):
    for attrs in [{'property':'og:image'},{'name':'twitter:image'}]:
        tag = soup.find('meta', attrs=attrs)
        if tag and tag.get('content'):
            return urljoin(base, tag['content'])
    return None


def legal_pack(soup, base):
    for a in soup.find_all('a', href=True):
        if 'legal pack' in norm(a.get_text(' ', strip=True)).lower():
            return urljoin(base, a['href']), 'AVAILABLE'
    return None, 'NOT FOUND'


def nearest_text(a):
    node = a
    best = ''
    for _ in range(7):
        node = getattr(node, 'parent', None)
        if node is None: break
        txt = norm(node.get_text(' ', strip=True))
        if len(txt) > len(best) and len(txt) <= 2200:
            best = txt
    return best


def exact_lot(source, url, seed='', lot_number=None, force=False):
    soup = BeautifulSoup(fetch(url), 'lxml')
    h1 = soup.find('h1')
    title = soup.find('title')
    address = norm(h1.get_text(' ', strip=True)) if h1 else (norm(title.get_text(' ', strip=True)).split('|')[0] if title else url)
    main = soup.find('main') or soup.find('article')
    exact = norm(main.get_text(' ', strip=True)) if main else norm(soup.get_text(' ', strip=True))
    if 'login to see' in address.lower(): return None
    if not force and not commercial(address + ' ' + exact[:9000]): return None
    guide = parse_guide(exact) or parse_guide(seed)
    rent = parse_rent(exact)
    lp_url, lp_status = legal_pack(soup, url)
    return {
        'source_id': source + '|' + url,
        'auctioneer': source,
        'source_url': url,
        'address': address,
        'image_url': image_url(soup, url),
        'lot_number': lot_number,
        'guide_price': guide,
        'annual_rent': rent,
        'gross_yield': round(rent / guide * 100, 2) if rent and guide else None,
        'tenure': parse_tenure(exact),
        'vat_status': parse_vat(exact),
        'legal_pack_status': lp_status,
        'legal_pack_url': lp_url,
    }


def collect_ahl(max_guide):
    source = 'Auction House London'; url = 'https://auctionhouselondon.co.uk/commercial-property-for-sale'
    try:
        soup = BeautifulSoup(fetch(url), 'lxml'); seen=set(); lots=[]
        for a in soup.find_all('a', href=True):
            if '/lot/' not in a['href']: continue
            lot_url = urljoin(url, a['href'])
            if lot_url in seen: continue
            card = nearest_text(a); low = card.lower()
            if not any(x in low for x in ['commercial property','retail property','mixed use','mixed-use','commercial unit','retail unit','commercial building']): continue
            g = parse_guide(card)
            if g and g > max_guide: continue
            seen.add(lot_url)
            lot = exact_lot(source, lot_url, card, force=True)
            if lot and (lot['guide_price'] is None or lot['guide_price'] <= max_guide): lots.append(lot)
        return source,'OK',lots,f'Dedicated commercial page · {len(lots)} verified lots'
    except Exception as e:
        return source,'ERROR',[],str(e)


def collect_allsop(max_guide):
    source='Allsop Commercial'; url='https://www.allsop.co.uk/auctions/commercial-auctions/'
    try:
        soup=BeautifulSoup(fetch(url),'lxml'); seen=set(); lots=[]
        for a in soup.find_all('a', href=True):
            card=nearest_text(a); low=card.lower()
            if 'commercial' not in low or 'lot' not in low: continue
            lot_url=urljoin(url,a['href'])
            if lot_url in seen: continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(lot_url)
            lot=exact_lot(source,lot_url,card,force=True)
            if lot and (lot['guide_price'] is None or lot['guide_price']<=max_guide): lots.append(lot)
        return source,'OK',lots,f'Dedicated commercial catalogue · {len(lots)} verified lots'
    except Exception as e:
        return source,'ERROR',[],str(e)


def collect_pugh(max_guide):
    source='Pugh / BTG Eddisons'; base='https://www.pugh-auctions.com'
    try:
        seen=set(); lots=[]
        for page in range(1,16):
            url=base+f'/property-search?include-sold=off&order-results=date-desc&page={page}&style=list'
            soup=BeautifulSoup(fetch(url),'lxml'); found=0
            for a in soup.find_all('a', href=True):
                if '/property/' not in a['href']: continue
                found += 1
                lot_url=urljoin(base,a['href'])
                if lot_url in seen: continue
                card=nearest_text(a)
                if not commercial(card): continue
                g=parse_guide(card)
                if g and g>max_guide: continue
                seen.add(lot_url)
                lot=exact_lot(source,lot_url,card)
                if lot and (lot['guide_price'] is None or lot['guide_price']<=max_guide): lots.append(lot)
            if found==0 and page>3: break
        return source,'OK',lots,f'Exact-page commercial check · {len(lots)} verified lots'
    except Exception as e:
        return source,'ERROR',[],str(e)


def collect_bond_wolfe(max_guide):
    source='Bond Wolfe'; base='https://www.bondwolfe.com'; url=base+'/auctions/properties/'
    try:
        soup=BeautifulSoup(fetch(url),'lxml'); seen=set(); lots=[]
        for a in soup.find_all('a', href=True):
            card=nearest_text(a)
            if not commercial(card): continue
            lot_url=urljoin(base,a['href'])
            if lot_url in seen: continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(lot_url)
            lot=exact_lot(source,lot_url,card)
            if lot and (lot['guide_price'] is None or lot['guide_price']<=max_guide): lots.append(lot)
        return source,'OK',lots,f'Exact-page commercial check · {len(lots)} verified lots'
    except Exception as e:
        return source,'ERROR',[],str(e)


def collect_savills(max_guide):
    source='Savills Auctions'
    base='https://auctions.savills.co.uk'
    upcoming=base+'/upcoming-auctions'
    try:
        landing=BeautifulSoup(fetch(upcoming),'lxml')
        catalogues=[]

        # Find actual auction catalogue links from the upcoming-auctions page.
        for a in landing.find_all('a', href=True):
            href=a['href']
            label=norm(a.get_text(' ',strip=True)).lower()
            if '/auctions/' in href and ('catalogue' in label or 'view' in label):
                u=urljoin(base,href)
                if u not in catalogues:
                    catalogues.append(u)

        # Fallback in case Savills changes the anchor wording.
        if not catalogues:
            for a in landing.find_all('a', href=True):
                if '/auctions/' in a['href']:
                    u=urljoin(base,a['href'])
                    if u not in catalogues:
                        catalogues.append(u)

        lots=[]
        seen=set()
        commercial_sections=0
        checked=0

        for catalogue in catalogues[:4]:
            # Savills catalogue pages are paginated; page-1 contains a special
            # 'Commercial Section' card when a dedicated commercial section exists.
            cat_url=catalogue.rstrip('/')
            if not re.search(r'/page-\d+(?:/|$)',cat_url):
                page1=cat_url+'/page-1'
            else:
                page1=cat_url

            try:
                soup=BeautifulSoup(fetch(page1),'lxml')
            except Exception:
                soup=BeautifulSoup(fetch(catalogue),'lxml')

            section_url=None
            for a in soup.find_all('a',href=True):
                card=nearest_text(a)
                if 'commercial section' in card.lower():
                    href=urljoin(base,a['href'])
                    # Prefer Savills' own filtered commercial catalogue URL,
                    # e.g. /quantity-100/property_type-253/sort-by-0
                    if 'property_type-' in href or 'commercial' in card.lower():
                        section_url=href
                        break

            if section_url:
                commercial_sections+=1
                section_soup=BeautifulSoup(fetch(section_url),'lxml')
                force_commercial=True
            else:
                # Preliminary auctions may not yet expose the special section link.
                section_soup=soup
                force_commercial=False

            candidates=[]
            local_seen=set()
            for a in section_soup.find_all('a',href=True):
                href=a['href']
                lot_url=urljoin(base,href)
                if lot_url in local_seen or lot_url in seen:
                    continue

                card=nearest_text(a)
                low=card.lower()
                m=re.search(r'\bLot\s+(\d+[A-Z]?)\b',card,re.I)
                if not m:
                    continue
                if 'guide price' not in low:
                    continue
                if 'login to see' in low:
                    continue
                if not force_commercial and not commercial(card):
                    continue

                guide=parse_guide(card)
                if guide and guide>max_guide:
                    continue

                # Avoid pagination/filter/navigation links; a real lot link normally
                # carries the auction slug and a property-specific tail.
                if '/auctions/' not in lot_url and '/component/bidding/' not in lot_url:
                    continue

                local_seen.add(lot_url)
                seen.add(lot_url)
                candidates.append((lot_url,card,f"Lot {m.group(1)}"))

            # The commercial-filter page already gives us trustworthy commercial
            # provenance; exact pages are then used for rent/tenure/VAT/legal pack.
            for lot_url,card,lotno in candidates:
                checked+=1
                lot=exact_lot(source,lot_url,card,lotno,force=force_commercial)
                if lot and (lot['guide_price'] is None or lot['guide_price']<=max_guide):
                    lots.append(lot)

        return source,'OK',lots,(
            f'{commercial_sections} dedicated commercial section(s) found · '
            f'{checked} Savills commercial lots checked · {len(lots)} loaded'
        )
    except Exception as e:
        return source,'ERROR',[],str(e)

def collect_acuitus(max_guide):
    source='Acuitus'; base='https://www.acuitus.co.uk'; url=base+'/find-a-property/?which=sales'
    try:
        page=fetch(url)
        if 'full auction catalogue will be available' in page.lower():
            return source,'CATALOGUE_PENDING',[],'Next full catalogue not yet published'
        soup=BeautifulSoup(page,'lxml'); seen=set(); lots=[]
        for a in soup.find_all('a', href=True):
            card=nearest_text(a)
            if 'guide' not in card.lower() and 'yield' not in card.lower(): continue
            lot_url=urljoin(base,a['href'])
            if lot_url in seen: continue
            g=parse_guide(card)
            if g and g>max_guide: continue
            seen.add(lot_url)
            lot=exact_lot(source,lot_url,card,force=True)
            if lot and (lot['guide_price'] is None or lot['guide_price']<=max_guide): lots.append(lot)
        return source,'OK',lots,f'Commercial catalogue · {len(lots)} verified lots'
    except Exception as e:
        return source,'ERROR',[],str(e)


def scan_all(max_guide=300000):
    results=[collect_ahl(max_guide),collect_allsop(max_guide),collect_pugh(max_guide),collect_bond_wolfe(max_guide),collect_savills(max_guide),collect_acuitus(max_guide)]
    replace_snapshot(results)
    return results


init_db()

st.markdown('''
<style>
header[data-testid="stHeader"],div[data-testid="stToolbar"],#MainMenu{display:none!important}
.block-container{max-width:1500px;padding:.2rem .25rem 1.2rem!important}.stApp{background:#0b1018;color:#f6f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;background:#121925;border:1px solid #29344a;border-radius:11px;padding:9px 10px;margin-bottom:4px}
.brand{font-size:1.05rem;font-weight:950}.brand b{color:#f2c94c}.sub{font-size:.45rem;color:#95a3b7;margin-top:2px}.count{font-size:.42rem;border:1px solid #2e8b5c;color:#9ae6b4;border-radius:999px;padding:4px 5px}
.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px}.card{background:#121925;border:1px solid #29344a;border-radius:9px;overflow:hidden}.card img{width:100%;height:86px;object-fit:cover}.noimg{height:55px;display:grid;place-items:center;background:#172131;color:#718095;font-size:.35rem}
.cb{padding:5px}.src{font-size:.32rem;color:#f2c94c;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.addr{font-size:.52rem;font-weight:850;line-height:1.14;min-height:2.3em;margin:2px 0 4px}.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:2px}.metric{background:#171f2d;border-radius:5px;padding:3px}.metric span{display:block;color:#8f9db0;font-size:.27rem}.metric b{font-size:.42rem}.meta{font-size:.28rem;color:#a8b5c7;margin-top:3px}.action{display:block;text-align:center;text-decoration:none;background:#f2c94c;color:#171208;border-radius:5px;padding:4px;margin-top:4px;font-size:.35rem;font-weight:900}
@media(max-width:800px){.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.card img{height:64px}}
</style>
''',unsafe_allow_html=True)

if count_all()==0:
    with st.status('Scanning commercial auction sources…', expanded=False) as status:
        scan_all(300000)
        status.update(label=f'Scan complete - {count_all()} commercial candidates', state='complete')

source_rows=get_sources()
healthy=sum(1 for s in source_rows if s['status']=='OK')
hero_html = '<div class="hero"><div><div class="brand">AUCTION <b>SNIPER</b></div><div class="sub">UK commercial &amp; mixed-use auction opportunities</div></div><div class="count">{} lots - {} sources</div></div>'.format(count_all(), healthy)
st.markdown(hero_html, unsafe_allow_html=True)

with st.expander('⚙️ Filters & refresh', expanded=False):
    a,b=st.columns(2)
    max_price=a.number_input('Maximum guide (£)',value=250000,step=5000)
    min_yield=b.number_input('Minimum GIY (%)',value=10.0,step=.5)
    include_unknown=st.toggle('Include unknown rent/yield',value=True)
    if st.button('🔄 Rebuild current snapshot',type='primary',use_container_width=True):
        with st.spinner('Scanning all sources…'):
            scan_all(300000)
        st.rerun()

max_price=locals().get('max_price',250000);min_yield=locals().get('min_yield',10.0);include_unknown=locals().get('include_unknown',True)
lots_tab,sources_tab=st.tabs(['🎯 Lots','📡 Sources'])

with sources_tab:
    for s in get_sources():
        icon='✅' if s['status']=='OK' else ('⏳' if s['status']=='CATALOGUE_PENDING' else '⚠️')
        st.write(f"{icon} **{s['source']}** - {s['lots_seen']} lots")
        st.caption(s['message'])

def money(v): return 'Unknown' if v is None else f'£{v:,.0f}'
def pct(v): return 'Unknown' if v is None else f'{v:.1f}%'

with lots_tab:
    lots=get_lots(max_price,min_yield,include_unknown)
    st.caption(f'{len(lots)} matching commercial / mixed-use lots')
    cards=[]
    for x in lots:
        img=f'<img src="{html.escape(x["image_url"])}">' if x.get('image_url') else '<div class="noimg">NO IMAGE</div>'
        ceiling=x['annual_rent']/.10 if x.get('annual_rent') else None
        meta=' · '.join(v for v in [x.get('tenure'),f'VAT {x["vat_status"]}' if x.get('vat_status')!='UNKNOWN' else None,'Legal pack' if x.get('legal_pack_status')=='AVAILABLE' else None] if v)
        cards.append('<div class="card">'+img+'<div class="cb">'
            +f'<div class="src">{html.escape(x["auctioneer"])} · {html.escape(x.get("lot_number") or "Lot TBC")}</div>'
            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide</span><b>{money(x.get("guide_price"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("annual_rent"))}</b></div>'
            +f'<div class="metric"><span>GIY</span><b>{pct(x.get("gross_yield"))}</b></div>'
            +f'<div class="metric"><span>10% ceiling</span><b>{money(ceiling)}</b></div></div>'
            +f'<div class="meta">{html.escape(meta)}</div>'
            +f'<a class="action" target="_blank" href="{html.escape(x["source_url"])}">Original lot ↗</a></div></div>')
    st.markdown('<div class="cards">'+''.join(cards)+'</div>',unsafe_allow_html=True)
