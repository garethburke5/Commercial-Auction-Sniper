from pathlib import Path
import re

p = Path('app.py')
s = p.read_text(encoding='utf-8')

s = re.sub(r'BUILD = "[^"]+"', 'BUILD = "V6.73-OPPORTUNITY-SUMMARIES"', s, count=1)

if 'from property_summary import build_opportunity_summary' not in s:
    s=s.replace('from collector_enrichment import extract_particulars, merge_enrichment',
                'from collector_enrichment import extract_particulars, merge_enrichment\nfrom property_summary import build_opportunity_summary',1)

new_load = r'''def load_rows():
    """Load exactly one source of truth: the persisted production collector snapshot.

    The Streamlit presentation layer must never merge hard-coded SEED rows or local
    refresh caches into production truth. Historical records remain in the snapshot,
    while the main board selects current/upcoming lots at render time.
    """
    snapshot_path=Path("data/properties.json")
    health=SOURCE_HEALTH
    updated="Collector snapshot unavailable"
    live_rows=[]
    if snapshot_path.exists():
        try:
            snap=json.loads(snapshot_path.read_text(encoding="utf-8"))
            for x in snap.get("properties") or []:
                live_rows.append(dict(
                    source=x.get("source"), lot=x.get("lot_number") or "Lot TBC",
                    date=x.get("auction_date"), address=x.get("address") or "",
                    guide=x.get("guide_price"), rent=x.get("annual_rent"),
                    tenure=x.get("tenure") or "UNKNOWN", vat=x.get("vat_status") or "UNKNOWN",
                    url=x.get("url") or "", desc=x.get("description") or "", image=x.get("image_url"),
                    legal_pack_status=x.get("legal_pack_status") or "UNKNOWN",
                    legal_pack_url=x.get("legal_pack_url"), status=x.get("status") or "Live",
                    area_sqft=x.get("area_sqft"), area_sqm=x.get("area_sqm"), site_area_acres=x.get("site_area_acres"),
                    tenant=x.get("tenant"), lease_term=x.get("lease_term"), lease_start=x.get("lease_start"),
                    lease_expiry=x.get("lease_expiry"), break_clause=x.get("break_clause"), break_status=x.get("break_status"),
                    rent_review=x.get("rent_review"), fri=x.get("fri"), erv=x.get("erv"), epc=x.get("epc"),
                    rateable_value=x.get("rateable_value"), service_charge=x.get("service_charge"), ground_rent=x.get("ground_rent"),
                    property_type=x.get("property_type"), occupation=x.get("occupation"), parking=x.get("parking"),
                    development_potential=x.get("development_potential"), asset_management=x.get("asset_management"),
                    refurbishment=x.get("refurbishment"), residential_conversion=x.get("residential_conversion"),
                    listed_status=x.get("listed_status"), covenant_rating=x.get("covenant_rating"), covenant_risk=x.get("covenant_risk"),
                    covenant_turnover=x.get("covenant_turnover"), guarantors=x.get("guarantors"), pitch=x.get("pitch"),
                    nearby_occupiers=x.get("nearby_occupiers"), source_id=x.get("source_id"),
                ))
            if snap.get("source_health"):
                health=snap["source_health"]
            generated=snap.get("generated_at")
            if generated:
                updated=f"Collector snapshot · {generated[:16].replace('T',' ')} UTC"
        except Exception:
            live_rows=[]
    return _clean_rows(live_rows),health,updated
'''

s, n = re.subn(r'def load_rows\(\):.*?\n\nRESIDENTIAL_EXACT_TYPES =', new_load + '\n\nRESIDENTIAL_EXACT_TYPES =', s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('load_rows patch failed')

new_refresh = r'''def refresh_market():
    """Presentation-layer refresh.

    Production collection is owned by run_collectors.py/GitHub Actions. The app must
    not run a second, divergent set of auction-house scrapers or write a competing
    cache. Re-read the canonical snapshot only.
    """
    rows,health,updated=load_rows()
    return {"updated":updated,"properties":rows,"health":health}
'''
s, n = re.subn(r'def refresh_market\(\):.*?\n\n\n# ---------------- DEEP EVIDENCE / SEMANTIC NORMALISATION ----------------', new_refresh + '\n\n\n# ---------------- DEEP EVIDENCE / SEMANTIC NORMALISATION ----------------', s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('refresh_market patch failed')

needle = 'rows,health,updated=load_rows()\ntry:\n'
marker = '# The main board is CURRENT/UPCOMING only.'
replacement = '''rows,health,updated=load_rows()\n# The main board is CURRENT/UPCOMING only. Completed, sold-prior and withdrawn\n# records remain preserved in data/properties.json for history/research, but they\n# must not pollute the live deal-scanning board.\nfrom datetime import date as _date\n_all_snapshot_rows=list(rows)\n_today=_date.today().isoformat()\ndef _is_current_board_row(r):\n    status=str(r.get("status") or "").strip().lower()\n    if status in {"archived","sold prior","withdrawn","withdrawn prior","auction ended","completed"}:\n        return False\n    d=str(r.get("date") or "").strip()\n    if re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}",d) and d < _today:\n        return False\n    return True\nrows=[r for r in rows if _is_current_board_row(r)]\ntry:\n'''
if marker not in s:
    if needle not in s:
        raise SystemExit('render board insertion point missing')
    s=s.replace(needle,replacement,1)

s=s.replace('st.tabs(["🎯 All properties","📡 Source health"])', 'st.tabs(["🎯 Current properties","📡 Source health"])', 1)
s=s.replace('ALL verified current properties', 'current/upcoming verified properties', 1)

# Add compact value-add card styling once.
if '.oppTitle{' not in s:
    s=s.replace('.addr{font-size:.90rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:5px 0 9px;color:#ffffff}',
                '.oppTitle{font-size:.66rem;font-weight:950;letter-spacing:.025em;color:#f5d45e;margin:5px 0 3px;line-height:1.2}.oppFacts{font-size:.62rem;color:#d4dfec;line-height:1.32;margin:0 0 6px}.oppFacts b{color:#eef4fb}.addr{font-size:.90rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:4px 0 7px;color:#ffffff}',1)
    s=s.replace('.addr{font-size:.70rem;line-height:1.23;min-height:3.35em;margin:4px 0 6px}',
                '.oppTitle{font-size:.50rem;margin:4px 0 2px}.oppFacts{font-size:.47rem;line-height:1.25;margin-bottom:5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.addr{font-size:.70rem;line-height:1.23;min-height:3.35em;margin:3px 0 5px}',1)

# Generate the opportunity headline and the most decision-useful facts before rendering each card.
summary_needle='''        _address=str(x.get("address") or "").strip()\n        _map_query=urllib.parse.quote_plus(_address)'''
summary_replacement='''        _address=str(x.get("address") or "").strip()\n        _opp_title,_opp_highlights=build_opportunity_summary(x)\n        _opp_facts=" · ".join(_opp_highlights[:3])\n        _map_query=urllib.parse.quote_plus(_address)'''
if '_opp_title,_opp_highlights=build_opportunity_summary(x)' not in s:
    if summary_needle not in s:
        raise SystemExit('opportunity summary insertion point missing')
    s=s.replace(summary_needle,summary_replacement,1)

card_needle='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
card_replacement='''            +f'<div class="src">{html.escape(x["source"])} · {html.escape(x.get("lot") or "Lot TBC")}</div>'\n            +f'<div class="oppTitle">{html.escape(_opp_title)}</div>'\n            +(f'<div class="oppFacts">{html.escape(_opp_facts)}</div>' if _opp_facts else '')\n            +f'<div class="addr">{html.escape(x["address"])}</div><div class="metrics">' '''
if '<div class="oppTitle">' not in s:
    if card_needle not in s:
        raise SystemExit('card opportunity insertion point missing')
    s=s.replace(card_needle,card_replacement,1)

p.write_text(s,encoding='utf-8')
print('Patched app.py to canonical snapshot + current-only board + opportunity summaries')
