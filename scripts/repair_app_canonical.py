from pathlib import Path
import re

p = Path('app.py')
s = p.read_text(encoding='utf-8')

s = re.sub(r'BUILD = "[^"]+"', 'BUILD = "V6.75-CANONICAL-HEALTH"', s, count=1)

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

needle='''                    nearby_occupiers=x.get("nearby_occupiers"), source_id=x.get("source_id"),
                ))'''
repl='''                    nearby_occupiers=x.get("nearby_occupiers"), source_id=x.get("source_id"),
                    snapshot_bucket=x.get("_snapshot_bucket"),
                ))'''
if needle in s:
    s=s.replace(needle,repl,1)

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

if '.lifecycleBanner{' not in s:
    css_anchor='.cards{display:grid;'
    lifecycle_css='''.lifecycleBanner{margin:-1px -1px 7px;padding:6px 8px;border-radius:7px;text-align:center;font-size:.64rem;font-weight:1000;letter-spacing:.035em}.soldPriorBanner{background:#54212a;border:1px solid #a94b5c;color:#ffdbe1}.historicBanner{background:#263140;border:1px solid #53647a;color:#d8e1ec}.historyIntro{font-size:.78rem;color:#aebbd0;margin:0 0 9px}.historicalCard{opacity:.90}.historicalCard .action{background:#334155;color:#eef3f8!important}@media(max-width:650px){.lifecycleBanner{font-size:.48rem;padding:5px 4px;margin-bottom:5px}.historyIntro{font-size:.58rem}}'''
    if css_anchor not in s: raise SystemExit('card CSS anchor missing')
    s=s.replace(css_anchor,lifecycle_css+css_anchor,1)

s=s.replace('lots_tab,sources_tab=st.tabs(["🎯 Current properties","📡 Source health"])',
            'lots_tab,sold_tab,history_tab,sources_tab=st.tabs(["🎯 Current properties",f"🏷️ Sold prior ({len(_sold_prior_rows)})",f"🗂️ History ({len(_historic_rows)})","📡 Source health"])',1)

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

# The old presentation layer carried Aug/Sep hard-coded minimum counts. They are
# stale by definition once new catalogues publish and can falsely mark healthy current
# sources as missing. Production collector telemetry is now the only count authority.
s=re.sub(r'EXPECTED_CURRENT_COUNTS\s*=\s*\{.*?\}\n\n', 'EXPECTED_CURRENT_COUNTS = {}\n\n', s, count=1, flags=re.S)

# Replace the stale capture audit with a canonical active-board audit. Count
# reconciliation itself is enforced in CI against source_health.expected_count.
audit_pattern=r'''\s*st\.info\("INTERMEDIATE BUILD — live catalogue enrichment is enabled; source audit below should be checked after Refresh market\."\)\n\s*st\.markdown\("#### Capture audit"\)\n\s*st\.caption\("Expected counts are minimum independently verified current commercial/mixed-use lots\. Falling below them is a release failure\."\)\n\s*audit_rows=\[\]\n\s*for src,a in sorted\(source_audit\.items\(\)\):.*?\n\s*if audit_rows:\n\s*st\.dataframe\(audit_rows,use_container_width=True,hide_index=True\)'''
audit_replacement='''
    st.markdown("#### Production capture audit")
    st.caption("Current-board presentation checks. Catalogue count reconciliation and collector failures are enforced before the snapshot is published.")
    health_by_source={str(h.get("source") or ""):h for h in health if isinstance(h,dict)}
    audit_rows=[]
    for src,a in sorted(source_audit.items()):
        image_pct=(100*a["images"]/a["properties"]) if a["properties"] else 0
        h=health_by_source.get(src,{})
        collector_status=str(h.get("status") or "UNKNOWN")
        audit_status=("❌ CHECK" if a["commercial_flags"]>0 or image_pct<70
                      else "⚠️ PARTIAL" if image_pct<100
                      else "✅ GOOD")
        if collector_status in {"FAILED","NOT IMPLEMENTED","MISSING"}: audit_status="❌ COLLECTOR"
        audit_rows.append({
            "Source":src,
            "Current lots":a["properties"],
            "Images":a["images"],
            "Image coverage":f"{image_pct:.0f}%",
            "Exact pages":f'{a["exact_pages"]}/{a["properties"]}',
            "Residential flags":a["commercial_flags"],
            "Collector status":collector_status,
            "Audit":audit_status,
        })
    if audit_rows:
        st.dataframe(audit_rows,use_container_width=True,hide_index=True)'''
s,n=re.subn(audit_pattern,audit_replacement,s,count=1,flags=re.S)
if n==0 and 'INTERMEDIATE BUILD — live catalogue enrichment is enabled' in s:
    raise SystemExit('canonical source audit replacement failed')

# Snapshot source-health dictionaries use `message`, not legacy `note`. Render both
# safely and show the collector's own count reconciliation rather than a stale UI map.
health_pattern=r'''\s*actual_counts=\{\}\n\s*for p in rows:\n\s*actual_counts\[p\["source"\]\]=actual_counts\.get\(p\["source"\],0\)\+1\n\s*for h in health:.*?st\.markdown\(f'<div class="statusrow">\{icon\} <b>\{html\.escape\(h\["source"\]\)\}</b> — \{html\.escape\(h\["status"\]\)\}<br><small>\{html\.escape\(h\["note"\]\)\}</small></div>',unsafe_allow_html=True\)'''
health_replacement='''
    actual_counts={}
    for p in rows:
        actual_counts[p["source"]]=actual_counts.get(p["source"],0)+1
    for raw_h in health:
        h=dict(raw_h) if isinstance(raw_h,dict) else {}
        src=str(h.get("source") or "Unknown")
        status=str(h.get("status") or "UNKNOWN")
        message=str(h.get("message") or h.get("note") or "")
        loaded=actual_counts.get(src,0)
        seen=h.get("lots_seen")
        expected=h.get("expected_count")
        count_text=(f"collector {seen}/{expected}" if expected not in (None,0) else f"collector {seen}" if seen is not None else "collector count unavailable")
        detail=f"{loaded} current board · {count_text}"
        if message: detail += " · " + message
        icon="✅" if status=="LIVE" else ("⏳" if "PENDING" in status or "EARLY" in status else "⚠️" if status=="DEGRADED" else "❌" if status in {"FAILED","MISSING","NOT IMPLEMENTED"} else "ℹ️")
        st.markdown(f'<div class="statusrow">{icon} <b>{html.escape(src)}</b> — {html.escape(status)}<br><small>{html.escape(detail)}</small></div>',unsafe_allow_html=True)'''
s,n=re.subn(health_pattern,health_replacement,s,count=1,flags=re.S)
if n==0 and 'h["note"]' in s:
    raise SystemExit('canonical source health replacement failed')

p.write_text(s, encoding='utf-8')
print('Patched app.py with lifecycle history and canonical source-health telemetry')
