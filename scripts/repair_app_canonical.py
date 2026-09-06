from pathlib import Path
import re

p = Path('app.py')
s = p.read_text(encoding='utf-8')

s = re.sub(r'BUILD = "[^"]+"', 'BUILD = "V6.74-MARKET-HISTORY"', s, count=1)

if 'from property_summary import build_opportunity_summary' not in s:
    anchor = 'from collector_enrichment import extract_particulars, merge_enrichment'
    if anchor not in s:
        raise SystemExit('property summary import anchor missing')
    s = s.replace(anchor, anchor + '\nfrom property_summary import build_opportunity_summary', 1)

if 'snapshot_path=Path("data/properties.json")' not in s:
    raise SystemExit('canonical snapshot loader missing')

# load_rows must expose the archive as market intelligence, not silently discard it.
old = '''            for x in snap.get("properties") or []:
                live_rows.append(dict('''
new = '''            snapshot_rows=[]
            for _bucket,_rows in (("CURRENT",snap.get("properties") or []),("ARCHIVE",snap.get("archive") or [])):
                for x in _rows:
                    _copy=dict(x)
                    _copy["_snapshot_bucket"]=_bucket
                    snapshot_rows.append(_copy)
            for x in snapshot_rows:
                live_rows.append(dict('''
if old in s:
    s=s.replace(old,new,1)

# Preserve the canonical lifecycle and snapshot bucket in presentation rows.
needle='''                    nearby_occupiers=x.get("nearby_occupiers"), source_id=x.get("source_id"),
                ))'''
repl='''                    nearby_occupiers=x.get("nearby_occupiers"), source_id=x.get("source_id"),
                    snapshot_bucket=x.get("_snapshot_bucket"),
                ))'''
if needle in s:
    s=s.replace(needle,repl,1)

# Keep current board strict, but retain all snapshot rows for separate history tabs.
needle='''_all_snapshot_rows=list(rows)
_today=_date.today().isoformat()'''
repl='''_all_snapshot_rows=list(rows)
_today=_date.today().isoformat()

def _market_lifecycle(r):
    status=str(r.get("status") or "").strip().upper().replace("_"," ")
    desc=str(r.get("desc") or "")
    if re.search(r"\\bSOLD\\s*PRIOR\\b|\\bSOLDPRIOR\\b", status+" "+desc, re.I): return "SOLD PRIOR"
    if re.search(r"\\bWITHDRAWN(?:\\s+PRIOR)?\\b", status+" "+desc, re.I): return "WITHDRAWN"
    d=str(r.get("date") or "").strip()
    if status in {"ARCHIVED","AUCTION ENDED","COMPLETED"} or (re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}",d) and d < _today): return "AUCTION ENDED / HISTORIC"
    if status=="STALE SOURCE": return "SOURCE UNAVAILABLE / VERIFY"
    return "CURRENT"

_sold_prior_rows=[r for r in _all_snapshot_rows if _market_lifecycle(r)=="SOLD PRIOR"]
_historic_rows=[r for r in _all_snapshot_rows if _market_lifecycle(r) in {"WITHDRAWN","AUCTION ENDED / HISTORIC","SOURCE UNAVAILABLE / VERIFY"}]'''
if needle in s:
    s=s.replace(needle,repl,1)

# Add lifecycle UI styles.
if '.lifecycleBanner{' not in s:
    css_anchor='.cards{display:grid;'
    lifecycle_css='''.lifecycleBanner{margin:-1px -1px 7px;padding:6px 8px;border-radius:7px;text-align:center;font-size:.64rem;font-weight:1000;letter-spacing:.035em}.soldPriorBanner{background:#54212a;border:1px solid #a94b5c;color:#ffdbe1}.historicBanner{background:#263140;border:1px solid #53647a;color:#d8e1ec}.historyIntro{font-size:.78rem;color:#aebbd0;margin:0 0 9px}.historicalCard{opacity:.90}.historicalCard .action{background:#334155;color:#eef3f8!important}@media(max-width:650px){.lifecycleBanner{font-size:.48rem;padding:5px 4px;margin-bottom:5px}.historyIntro{font-size:.58rem}}'''
    if css_anchor not in s: raise SystemExit('card CSS anchor missing')
    s=s.replace(css_anchor,lifecycle_css+css_anchor,1)

# Three user-facing lifecycle tabs.
s=s.replace('lots_tab,sources_tab=st.tabs(["🎯 Current properties","📡 Source health"])',
            'lots_tab,sold_tab,history_tab,sources_tab=st.tabs(["🎯 Current properties",f"🏷️ Sold prior ({len(_sold_prior_rows)})",f"🗂️ History ({len(_historic_rows)})","📡 Source health"])',1)

# Reusable compact historical cards. They preserve guide/rent/yield and evidence-led summary.
if 'def _render_market_history_cards(' not in s:
    anchor='''def money(v): return "—" if v is None else f"£{v:,.0f}"
def pct(v): return "—" if v is None else f"{v:.1f}%"
'''
    helper='''def money(v): return "—" if v is None else f"£{v:,.0f}"
def pct(v): return "—" if v is None else f"{v:.1f}%"

def _render_market_history_cards(items, sold_prior=False):
    if not items:
        st.info("No properties recorded in this section yet.")
        return
    cards=[]
    for x in sorted(items,key=lambda r:(str(r.get("date") or ""),str(r.get("source") or ""),str(r.get("lot") or "")),reverse=True):
        lifecycle=_market_lifecycle(x)
        title,highlights=build_opportunity_summary(x)
        facts=" · ".join(highlights[:3])
        y=x.get("yield")
        if y is None and x.get("guide") and x.get("rent"):
            y=100*float(x["rent"])/float(x["guide"])
        image=_safe_card_image_src(x.get("source"),x.get("image"))
        url=html.escape(str(x.get("url") or ""),quote=True)
        preview=(f'<a class="previewLink" href="{url}" target="_blank" rel="noopener noreferrer"><img class="preview" src="{html.escape(image,quote=True)}" loading="lazy" referrerpolicy="no-referrer"></a>' if image and url else '<div class="preview noimg">Photo unavailable</div>')
        banner=("SOLD PRIOR — NOT AVAILABLE" if sold_prior else lifecycle)
        banner_class="soldPriorBanner" if sold_prior else "historicBanner"
        cards.append('<div class="card historicalCard">'+preview+'<div class="cb">'
            +f'<div class="lifecycleBanner {banner_class}">{html.escape(banner)}</div>'
            +f'<div class="src">{html.escape(str(x.get("source") or ""))} · {html.escape(str(x.get("lot") or "Lot TBC"))}</div>'
            +f'<div class="oppTitle">{html.escape(title)}</div>'
            +(f'<div class="oppFacts">{html.escape(facts)}</div>' if facts else '')
            +f'<div class="addr">{html.escape(str(x.get("address") or ""))}</div><div class="metrics">'
            +f'<div class="metric"><span>Guide at listing</span><b>{money(x.get("guide"))}</b></div>'
            +f'<div class="metric"><span>Rent p.a.</span><b>{money(x.get("rent"))}</b></div>'
            +f'<div class="metric yieldMetric"><span>GIY at guide</span><b>{pct(y)}</b></div>'
            +'<div class="metric"><span>Tenure</span><b>'+html.escape(str(x.get("tenure") or "—").upper())+'</b></div></div>'
            +f'<div class="meta">Auction date {html.escape(str(x.get("date") or "—"))}</div>'
            +_facts_html(x)
            +(f'<a class="action" target="_blank" rel="noopener noreferrer" href="{url}">Open archived/source page ↗</a>' if url else '')
            +'</div></div>')
    st.markdown('<div class="cards">'+''.join(cards)+'</div>',unsafe_allow_html=True)
'''
    if anchor not in s: raise SystemExit('money/pct anchor missing')
    s=s.replace(anchor,helper,1)

# Insert sold-prior and general history sections immediately before source-health diagnostics.
if 'with sold_tab:' not in s:
    anchor='# Source-health diagnostics execute only after the property board has been emitted.'
    sections='''with sold_tab:
    st.markdown('<div class="historyIntro"><b>Sold prior / unavailable.</b> These lots were positively identified as sold before auction. They are retained as market intelligence and are not available opportunities.</div>',unsafe_allow_html=True)
    _render_market_history_cards(_sold_prior_rows,sold_prior=True)

with history_tab:
    st.markdown('<div class="historyIntro"><b>Historical auction intelligence.</b> Completed, withdrawn and otherwise unavailable catalogue records are retained for comparable evidence. Status describes what we know; it does not imply a sale unless explicitly marked Sold Prior.</div>',unsafe_allow_html=True)
    _render_market_history_cards(_historic_rows,sold_prior=False)

'''
    if anchor not in s: raise SystemExit('source health anchor missing')
    s=s.replace(anchor,sections+anchor,1)

p.write_text(s, encoding='utf-8')
print('Patched app.py with opportunity summaries and lifecycle market history')
