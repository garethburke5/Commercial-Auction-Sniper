from pathlib import Path
import re, py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.37-STRETTONS-YIELD"',s,count=1)

# Strettons property photos are not emitted as normal <img> elements.
# They are embedded in page data as ggfx ... /api_sources/<id>/images/*_web_medium.jpeg.
# Put that exact pattern ahead of agent/headshot/logo candidates.
fn_start=s.find('def _strettons_exact_image(')
if fn_start < 0:
    raise SystemExit('Strettons image function missing')
fn_end=s.find('\n@st.cache_data',fn_start)
if fn_end < 0:
    raise SystemExit('Strettons image function end missing')
old=s[fn_start:fn_end]
new='''def _strettons_exact_image(soup_obj,page_url):
    """Extract the lot photo Strettons embeds in page data, not ordinary img tags."""
    raw=str(soup_obj)
    # Verified live markup example:
    # https://ggfx-strettons.s3.eu-west-2.amazonaws.com/i/api_sources/<property-id>/images/<id>_web_medium.jpeg
    embedded=re.findall(
        r'https://ggfx-strettons\\.s3\\.eu-west-2\\.amazonaws\\.com/i/api_sources/[^"\\'<>\\s]+?/images/[^"\\'<>\\s]+?\\.(?:jpe?g|png|webp)',
        raw,re.I
    )
    if embedded:
        # Prefer medium/large web property versions and never personnel assets.
        embedded=sorted(set(embedded),key=lambda u:("web_medium" in u.lower() or "web_large" in u.lower(),len(u)),reverse=True)
        return embedded[0]

    candidates=[]
    def add(raw_url,score=0):
        if not raw_url: return
        raw_url=str(raw_url).strip().split(' ')[0]
        if not raw_url: return
        u=urljoin(page_url,raw_url)
        low=u.lower()
        if any(x in low for x in ("logo","icon","avatar","agent","staff","headshot","map","marker","favicon","placeholder","sprite")):
            return
        if "ggfx-strettons.s3" in low: score+=6
        if "/api_sources/" in low and "/images/" in low: score+=20
        if any(x in low for x in ("property","auction","uploads","media")): score+=3
        candidates.append((score,u))
    for img in soup_obj.find_all("img"):
        for attr in ("src","data-src","data-lazy-src","data-original","data-image"):
            add(img.get(attr))
        for attr in ("srcset","data-srcset"):
            ss=img.get(attr)
            if ss:
                for part in ss.split(','): add(part.strip().split(' ')[0],1)
    candidates.sort(key=lambda x:x[0],reverse=True)
    return candidates[0][1] if candidates and candidates[0][0] >= 6 else None

'''
s=s[:fn_start]+new+s[fn_end:]

# Add a visible target-yield control to the compact top toolbar.
old_toolbar='''tool_a,tool_b,tool_space=st.columns([1.05,1.15,4.8],gap="small")
with tool_a:
    if st.button("↻ Update listings",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating current commercial auction listings and photos…"):
            refresh_market()
        st.rerun()
with tool_b:
    with st.popover("Refine properties",use_container_width=True):'''
new_toolbar='''tool_a,tool_b,tool_yield,tool_space=st.columns([1.05,1.15,1.25,3.55],gap="small")
with tool_a:
    if st.button("↻ Update listings",type="primary",use_container_width=True,help="Refresh current auction lots and property photos"):
        with st.spinner("Updating current commercial auction listings and photos…"):
            refresh_market()
        st.rerun()
with tool_b:
    with st.popover("Refine properties",use_container_width=True):'''
if old_toolbar not in s:
    raise SystemExit('top toolbar anchor missing')
s=s.replace(old_toolbar,new_toolbar,1)

# Insert target yield immediately after the refine-popover block, before tabs.
tabs_anchor='''lots_tab,sources_tab=st.tabs(["🎯 All properties","📡 Source health"])'''
if tabs_anchor not in s:
    raise SystemExit('tabs anchor missing')
yield_control='''with tool_yield:
    target_yield=st.number_input("Target yield (%)",min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",help="Change this to recalculate the maximum purchase price for every rented property")

'''
s=s.replace(tabs_anchor,yield_control+tabs_anchor,1)

# Dynamic max price at the selected target yield.
s=s.replace('''        ceiling=x["rent"]/.10 if x.get("rent") else None''','''        ceiling=x["rent"]/(target_yield/100.0) if x.get("rent") and target_yield else None''',1)
s=s.replace('''            +f'<div class="metric"><span>Max price @ 10% yield</span><b>{money(ceiling)}</b></div>' ''','''            +f'<div class="metric"><span>Max price @ {target_yield:g}% yield</span><b>{money(ceiling)}</b></div>' ''',1)

# Make the yield control read like a compact toolbar control rather than a large form field.
css='''\n/* V6.37 target yield toolbar */\ndiv[data-testid="stNumberInput"] label p{font-size:.67rem!important;font-weight:850!important;color:#dfe8f3!important}\ndiv[data-testid="stNumberInput"] input{font-weight:900!important}\n@media(max-width:650px){div[data-testid="stNumberInput"] label p{font-size:.56rem!important}}\n'''
anchor='</style>\n""",unsafe_allow_html=True)'
if anchor not in s: raise SystemExit('style anchor missing')
s=s.replace(anchor,css+'</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.37 applied: verified Strettons api_sources images + adjustable target yield')
