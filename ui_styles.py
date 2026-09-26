"""Readable controls and reports for both Auction Sniper themes."""
def board_styles(light=False):
    fg='#172033' if light else '#e8eef7'
    bg='#ffffff' if light else '#162130'
    border='#b8c4d3' if light else '#536780'
    return '''<style>
section[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
section[data-testid="stMain"] [data-testid="stTabs"] button{color:FG!important}
section[data-testid="stMain"] button[kind="secondary"]{background:BG!important;color:FG!important;border:1px solid BORDER!important}
section[data-testid="stMain"] button p{color:inherit!important}
section[data-testid="stMain"] button:disabled{opacity:.5!important}
section[data-testid="stMain"] input,section[data-testid="stMain"] textarea{color:#172033!important;background:#f8fafc!important;-webkit-text-fill-color:#172033!important}
section[data-testid="stMain"] [data-testid="stNumberInput"]{height:auto!important;margin:0!important}
section[data-testid="stMain"] [data-testid="stNumberInput"]>div{border-radius:7px!important;margin:0!important;box-shadow:none!important}
section[data-testid="stMain"] [data-testid="stNumberInput"] label{height:auto!important;display:block!important}
section[data-testid="stMain"] [data-testid="stNumberInput"] button{color:#172033!important}
section[data-testid="stMain"] [data-testid="stTextArea"] textarea{font-size:.9rem!important;line-height:1.6!important}
section[data-testid="stMain"] [data-testid="stFileUploaderDropzone"]{background:BG!important;color:FG!important}
section[data-testid="stMain"] [data-testid="stFileUploaderDropzone"] *{color:FG!important}
section[data-testid="stMain"] [data-testid="stVerticalBlock"]{gap:.55rem}
.hero{padding:14px 20px!important}.sub{color:FG!important;font-size:.68rem!important}
.pagerStatus,.pagerCount{color:FG!important;font-size:.78rem!important}
.pagerStatus b,.pagerCount b{color:FG!important}
@media(max-width:650px){
 .cards{grid-template-columns:1fr!important;gap:12px!important}
 .preview{height:210px!important}.cb{padding:12px!important}
 .addr{font-size:1rem!important;min-height:0!important}
 .src,.oppTitle{font-size:.8rem!important}.meta,.chip{font-size:.7rem!important}
 .metric span{font-size:.7rem!important}.metric b{font-size:.95rem!important}
 .analysis summary,.action,.mapAction,.historyAction a{font-size:.8rem!important}
 .fact span{font-size:.7rem!important}.fact b{font-size:.85rem!important}
}
</style>'''.replace('FG',fg).replace('BG',bg).replace('BORDER',border)
