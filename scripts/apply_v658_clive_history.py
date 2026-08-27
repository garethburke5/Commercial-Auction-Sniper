from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.57-STATIC-IMAGE-PROXY"','BUILD = "V6.58-CLIVE-HISTORY"',1)

# Add exact Clive Emson gallery extraction ahead of generic image scanning.
anchor="""def _v657_candidate_images(property_url, source):
    if not property_url:
        return []
    try:
        raw=fetch(property_url)
    except Exception:
        return []
    soup=BeautifulSoup(raw,'lxml')
    out=[]
"""
replacement="""def _v657_candidate_images(property_url, source):
    if not property_url:
        return []
    try:
        raw=fetch(property_url)
    except Exception:
        return []
    soup=BeautifulSoup(raw,'lxml')
    out=[]
"""
if anchor not in s: raise SystemExit('candidate function anchor missing')
s=s.replace(anchor,replacement,1)

needle="""    # Structured metadata first.
    for sel,attr in [
"""
insert=r'''    # Clive Emson uses predictable /AucNNN/pics/... image URLs on genuine lot pages.
    # Capture these before generic metadata so logos/placeholders cannot win.
    if (source or '').lower()=='clive emson':
        decoded=html.unescape(raw).replace('\\/','/')
        exact=[]
        # First inspect actual IMG/A elements, which preserves filenames containing spaces.
        for tag in soup.find_all(['img','a']):
            for attr in ('src','data-src','data-lazy-src','data-original','href'):
                v=tag.get(attr)
                if not v: continue
                vv=html.unescape(str(v)).replace('\\/','/')
                if re.search(r'/Auc\d+/pics/.+?\.(?:jpe?g|png|webp)(?:\?.*)?$',vv,re.I):
                    exact.append(urljoin(property_url,vv))
        # Then scan raw source for quoted Auc gallery paths.
        for m in re.findall(r'["\']([^"\']*/Auc\d+/pics/[^"\']+?\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']',decoded,re.I):
            exact.append(urljoin(property_url,m))
        for v in exact:
            if v not in out: out.append(v)

'''
if needle not in s: raise SystemExit('structured metadata anchor missing')
s=s.replace(needle,insert+needle,1)

# Rank exact Clive gallery images first.
old="""        elif 'clive emson' in src:
            if 'property' in lu or 'properties' in lu: sc+=70
            if 'lot' in lu: sc+=55
            if any(x in lu for x in ('gallery','photo','image')): sc+=30
"""
new="""        elif 'clive emson' in src:
            if re.search(r'/auc\\d+/pics/',lu): sc+=500
            if 'property' in lu or 'properties' in lu: sc+=70
            if 'lot' in lu: sc+=55
            if any(x in lu for x in ('gallery','photo','image')): sc+=30
"""
if old not in s: raise SystemExit('clive score anchor missing')
s=s.replace(old,new,1)

# Use a normal browser UA for remote image requests; Clive rejects the bot-style UA on image assets.
old="""            h=dict(HEADERS)
            h.update({'Accept':'image/avif,image/webp,image/apng,image/*,*/*;q=0.8','Referer':property_url or ''})
            r=requests.get(u,headers=h,timeout=15,allow_redirects=True)
"""
new="""            h={
                'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36',
                'Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                'Accept-Language':'en-GB,en;q=0.9',
                'Referer':property_url or '',
            }
            r=requests.get(u,headers=h,timeout=15,allow_redirects=True)
"""
if old not in s: raise SystemExit('image request headers anchor missing')
s=s.replace(old,new,1)

# If server-side localisation fails for Clive, preserve the exact gallery URL for client-side rendering.
old="""    return None


def _v657_localise_priority_rows(rows):
"""
new="""    if source=='Clive Emson':
        exact=_v657_candidate_images(property_url,source)
        for u in exact:
            if re.search(r'/Auc\\d+/pics/',u,re.I):
                return u
    return None


def _v657_localise_priority_rows(rows):
"""
if old not in s: raise SystemExit('local image fallback anchor missing')
s=s.replace(old,new,1)

# Visible previous-auction / sale-history search on every card.
old="""        _map_query=urllib.parse.quote_plus(str(x.get(\"address\") or \"\"))
        _maps_url=f\"https://www.google.com/maps/search/?api=1&query={_map_query}\"
        _image_src=_safe_card_image_src(x.get(\"source\"),x.get(\"image\"))
"""
new="""        _address=str(x.get(\"address\") or \"\").strip()
        _map_query=urllib.parse.quote_plus(_address)
        _maps_url=f\"https://www.google.com/maps/search/?api=1&query={_map_query}\"
        _history_query=urllib.parse.quote_plus(f'\"{_address}\" (auction OR sold OR sale OR guide OR lot)')
        _history_url=f\"https://www.google.com/search?q={_history_query}\"
        _image_src=_safe_card_image_src(x.get(\"source\"),x.get(\"image\"))
"""
if old not in s: raise SystemExit('map query card anchor missing')
s=s.replace(old,new,1)

old="""            +f'<div class=\"cardActions\"><a class=\"mapAction\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"{html.escape(_maps_url,quote=True)}\">Map / Street View ↗</a><a class=\"action\" target=\"_blank\" href=\"{html.escape(x[\"url\"])}\">Open property ↗</a></div>'
"""
new="""            +f'<div class=\"historyAction\"><a target=\"_blank\" rel=\"noopener noreferrer\" href=\"{html.escape(_history_url,quote=True)}\">Previous auctions / sale history ↗</a></div>'
            +f'<div class=\"cardActions\"><a class=\"mapAction\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"{html.escape(_maps_url,quote=True)}\">Map / Street View ↗</a><a class=\"action\" target=\"_blank\" href=\"{html.escape(x[\"url\"])}\">Open property ↗</a></div>'
"""
if old not in s: raise SystemExit('card actions anchor missing')
s=s.replace(old,new,1)

# Prevent browsers sending Auction Sniper as referrer when a direct Clive image fallback is used.
s=s.replace('<img class=\"preview\" src=\"{html.escape(_image_src,quote=True)}\" loading=\"lazy\">','<img class=\"preview\" src=\"{html.escape(_image_src,quote=True)}\" loading=\"lazy\" referrerpolicy=\"no-referrer\">')

css='''
/* V6.58 visible historical-sale research */
.historyAction{margin-top:7px}
.historyAction a{display:block;text-align:center;text-decoration:none!important;background:#101b28;color:#cbd8e8!important;border:1px solid #334862;border-radius:7px;padding:7px 7px;font-size:.63rem;font-weight:850}
.historyAction a:hover{border-color:#f2c94c;color:#f2c94c!important}
@media(max-width:650px){.historyAction{margin-top:5px}.historyAction a{font-size:.46rem;padding:5px 3px}}
'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.58 Clive exact gallery and visible auction history search applied')
