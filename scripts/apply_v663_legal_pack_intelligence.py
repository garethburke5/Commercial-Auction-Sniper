from pathlib import Path
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.61-DEEP-EVIDENCE"','BUILD = "V6.63-LEGAL-PACK-INTELLIGENCE"')
needle='from bs4 import BeautifulSoup\n'
if 'from eig_client import EIGClient' not in s:
    s=s.replace(needle, needle+'try:\n    from eig_client import EIGClient\nexcept Exception:\n    EIGClient=None\n')
seedneedle='SEED = [\n'
if 'EIG_KNOWN_PACKS' not in s:
    s=s.replace(seedneedle, 'EIG_KNOWN_PACKS = {\n    "8 red street, carmarthen": "1433491",\n}\n\n'+seedneedle)
anchor='def _facts_html(p):\n'
helpers=r'''def _legal_pack_identity(p):
    address=(p.get("address") or "").lower()
    pack_id=p.get("eig_pack_id")
    if not pack_id:
        for key,val in EIG_KNOWN_PACKS.items():
            if key in address:
                pack_id=val; break
    return pack_id

def _legal_pack_status(p):
    if p.get("legal_analysis"): return "Legal Pack Analysis ✓"
    if _legal_pack_identity(p) or p.get("legal_pack_url"): return "Analyse Legal Pack"
    return None

def _legal_pack_html(p):
    status=_legal_pack_status(p)
    if not status: return ""
    analysed=p.get("legal_analysis") or {}
    if analysed:
        rows=[]
        for k in ("Passing rent","Tenant","Lease","EPC","VAT","Title","Special conditions"):
            if analysed.get(k): rows.append(f'<div class="fact"><span>{html.escape(k)}</span><b>{html.escape(str(analysed[k]))}</b></div>')
        warnings=analysed.get("warnings") or []
        warn=''.join(f'<p>⚠ {html.escape(str(w))}</p>' for w in warnings)
        return '<details class="analysis legalIntel"><summary>Legal Pack Analysis ✓</summary><div class="factgrid">'+''.join(rows)+'</div><div class="iread">'+warn+'</div></details>'
    return '<div class="legalPackReady">🔎 '+html.escape(status)+'</div>'

def _eig_manifest_on_demand(pack_id):
    if not EIGClient: raise RuntimeError("Legal-pack client unavailable")
    try:
        email=st.secrets["EIG_EMAIL"]; password=st.secrets["EIG_PASSWORD"]
    except Exception:
        raise RuntimeError("EIG credentials are not configured")
    client=EIGClient(email,password)
    return client.pack(pack_id)

'''
if 'def _legal_pack_identity(p):' not in s:
    s=s.replace(anchor, helpers+anchor)
old='            +_facts_html(x)\n            +f\'<div class="historyAction">'
new='            +_facts_html(x)\n            +_legal_pack_html(x)\n            +f\'<div class="historyAction">'
s=s.replace(old,new)
end="    st.markdown('<div class=\"cards\">'+\"\".join(cards)+'</div>',unsafe_allow_html=True)"
addition=r'''    st.markdown('<div class="cards">'+"".join(cards)+'</div>',unsafe_allow_html=True)

    with st.expander("Legal Pack Intelligence · development test", expanded=False):
        st.caption("On-demand analysis only. Auction Sniper does not bulk-crawl authenticated legal packs.")
        if st.button("Analyse 8 Red Street legal pack", key="eig_test_1433491"):
            try:
                with st.spinner("Opening authorised legal pack…"):
                    title,docs=_eig_manifest_on_demand("1433491")
                st.success(f"Legal pack opened · {len(docs)} documents found")
                if title: st.write(title)
                priority=[d for d in docs if d.priority<=30]
                st.write("Priority due-diligence documents:")
                for d in priority[:20]:
                    flag="⚠ " if d.priority==12 else ""
                    st.write(f"{flag}{d.name}")
                if any(d.priority==12 for d in docs):
                    st.warning("Legal dispute/court documents present — review required. No conclusion is inferred until the documents are read.")
            except Exception as e:
                st.error(f"Legal pack connection failed: {e}")'''
if 'eig_test_1433491' not in s:
    s=s.replace(end,addition)
p.write_text(s,encoding='utf-8')
print('patched', 'V6.63-LEGAL-PACK-INTELLIGENCE' in s, 'eig_test_1433491' in s)
# workflow-trigger touch v2
