import streamlit as st
from db import init_db, get_lots, get_scan_status

st.set_page_config(page_title="Commercial Auction Sniper", page_icon="🎯", layout="wide")
init_db()

st.title("🎯 Commercial Auction Sniper")
st.caption("UK commercial & mixed-use auction intelligence")

a,b,c,d=st.columns(4)
max_price=a.number_input("Target max price (£)",value=250000,step=5000)
min_yield=b.number_input("Minimum GIY (%)",value=10.0,step=.5)
view=c.selectbox("View",["All","New / changed","Watchlist"])
show_unknown=d.toggle("Show unpriced / yield unknown",value=True)

tabs=st.tabs(["🎯 Sniper Board","📡 Source Health"])

with tabs[1]:
    scans=get_scan_status()
    if not scans:
        st.info("No live scan has run yet.")
    else:
        for s in scans:
            icon="✅" if s["status"]=="OK" else ("⏳" if s["status"]=="CATALOGUE_PENDING" else "⚠️")
            st.write(f'{icon} **{s["source"]}** — {s["status"]} — {s["lots_seen"]} lots — {s["message"] or ""}')

with tabs[0]:
    lots=get_lots(max_price,min_yield)
    if not lots:
        st.info("No matching live lots are in the database yet. Run the first live scan.")
    for x in lots:
        if not show_unknown and (x["guide_price"] is None or x["gross_yield"] is None):
            continue
        with st.container(border=True):
            image,body=st.columns([1,2])
            with image:
                if x["image_url"]:
                    st.image(x["image_url"],use_container_width=True)
                else:
                    st.caption("Image not available")
            with body:
                st.subheader(x["address"])
                st.caption(f'{x["auctioneer"]} · {x["auction_date"] or "Date TBC"} · {x["lot_number"] or "Lot TBC"} · {x["status"]}')
                q,w,e,r=st.columns(4)
                q.metric("Guide",f'£{x["guide_price"]:,.0f}' if x["guide_price"] else "UNKNOWN")
                w.metric("Rent p.a.",f'£{x["annual_rent"]:,.0f}' if x["annual_rent"] else "UNKNOWN")
                e.metric("GIY",f'{x["gross_yield"]:.1f}%' if x["gross_yield"] is not None else "UNKNOWN")
                ceiling=x["annual_rent"]/.10 if x["annual_rent"] else None
                r.metric("10% ceiling",f'£{ceiling:,.0f}' if ceiling else "UNKNOWN")
                st.write(
                    f'**Tenure:** {x["tenure"] or "UNKNOWN"} | '
                    f'**VAT:** {x["vat_status"] or "UNKNOWN"} | '
                    f'**TOGC:** {x["togc_status"] or "UNKNOWN"} | '
                    f'**Legal pack:** {x["legal_pack_status"] or "UNKNOWN"}'
                )
                buttons=st.columns(2)
                buttons[0].link_button("View original lot ↗",x["source_url"])
                if x.get("legal_pack_url"):
                    buttons[1].link_button("Open legal pack ↗",x["legal_pack_url"])
