"""Card navigation for source documents and the uploaded-document analyser."""
from html import escape
from urllib.parse import urlsplit


def legal_pack_links(row):
    url=str(row.get('legal_pack_url') or '')
    if urlsplit(url).scheme not in {'https','http'}:
        url=str(row.get('url') or '')
        label='Legal pack on auctioneer site ↗'
    else:
        label='Open auctioneer legal pack ↗'
    source=(f'<a target="_blank" rel="noopener noreferrer" href="{escape(url,quote=True)}">{label}</a>'
            if urlsplit(url).scheme in {'https','http'} else '')
    return '<div class="legalPackReady research">'+source+'<a href="#buyer-due-diligence">Analyse downloaded files ↓</a></div>'
