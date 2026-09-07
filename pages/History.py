import streamlit as st

from history_v2 import history_panel_html, find_history

st.set_page_config(page_title='Auction History · Auction Sniper', page_icon='↻', layout='wide', initial_sidebar_state='collapsed')

st.markdown('''
<style>
.historyV2{max-width:980px;margin:0 auto;color:#e9eef7}.historyV2 h3{font-size:1.5rem;margin:.2rem 0 1rem}.historyEvent{background:#101b2b;border:1px solid #31455e;border-radius:14px;padding:15px 16px;margin:12px 0;line-height:1.65}.historyEvent b{color:#fff}.historyEvidence{margin-top:8px}.historyEvidence a,.historyV2 a{color:#ffd34e;text-decoration:none;font-weight:700}.historyEvidence a:hover,.historyV2 a:hover{text-decoration:underline}.historyBack{margin-bottom:16px}.historyBack a{color:#d9e5f6;text-decoration:none;font-weight:700}.historyNote{max-width:980px;margin:0 auto 12px;color:#9fb0c5;font-size:.9rem}
</style>
''', unsafe_allow_html=True)

address = str(st.query_params.get('address') or '').strip()

st.markdown('<div class="historyBack"><a href="/">← Back to Auction Sniper</a></div>', unsafe_allow_html=True)

if not address:
    st.title('Previous auctions / sale history')
    st.info('Open this page from a property card to see matched auction history.')
else:
    matches = find_history(address, include_possible=True, limit=50)
    strong = sum(1 for m in matches if m.get('match_level') in ('EXACT','HIGH','PROBABLE'))
    possible = sum(1 for m in matches if m.get('match_level') == 'POSSIBLE_RELATED')
    st.markdown(
        f'<div class="historyNote">Internal database matches: {strong} · Possible related records: {possible}. '
        'Historic facts are shown with auctioneer evidence links where available.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(history_panel_html(address), unsafe_allow_html=True)
