from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

s=s.replace('BUILD = "V6.26-PRODUCTION-INTEGRATION"','BUILD = "V6.27-COMPACT-PRODUCTION"',1)

# Pugh pages often contain a direct BTG exact-lot link but not the BTG gallery
# markup themselves. If exact gallery discovery fails on the Pugh page, follow
# that exact BTG link and select the matching property image.
old='''        if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
            gallery=_btg_gallery_images(s,url)
            if gallery:
                image=gallery[0]
'''
new='''        if "btgeddisonspropertyauctions.com" in (url or "").lower() or "pugh-auctions.com" in (url or "").lower():
            gallery=_btg_gallery_images(s,url)
            if gallery:
                image=gallery[0]
            elif "pugh-auctions.com" in (url or "").lower():
                # Legacy Pugh page -> exact BTG lot page -> exact gallery.
                for a in s.find_all("a",href=True):
                    exact=urljoin(url,a["href"])
                    if "btgeddisonspropertyauctions.com/properties/" not in exact.lower():
                        continue
                    try:
                        bs=BeautifulSoup(fetch(exact),"lxml")
                        g=_btg_gallery_images(bs,exact)
                        if g:
                            image=g[0]
                            break
                    except Exception:
                        pass
'''
if old not in s:
    raise SystemExit('BTG image block anchor not found')
s=s.replace(old,new,1)

old_css='''.block-container{max-width:1420px;padding:1.1rem 1.35rem 2.5rem!important}
.stApp{background:#0a1019;color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:18px;background:linear-gradient(135deg,#151f2e,#0e1622);border:1px solid #2b3a50;border-radius:16px;padding:20px 22px;margin-bottom:12px;box-shadow:0 8px 28px rgba(0,0,0,.18)}
.brand{font-size:1.55rem;font-weight:950;letter-spacing:-.02em}.brand b{color:#f2c94c}.sub{font-size:.78rem;color:#9cacc0;margin-top:5px}
.badge{font-size:.72rem;border:1px solid #2e8b5c;color:#a8f0c4;background:#0d2119;border-radius:999px;padding:7px 10px;white-space:nowrap;font-weight:750}
 .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.card{background:#121b29;border:1px solid #26364b;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.14);transition:transform .15s ease,border-color .15s ease}
.card:hover{transform:translateY(-2px);border-color:#455b79}
.preview{display:block;width:100%;height:220px;object-fit:cover;background:#172131}
.noimg{display:grid;place-items:center;color:#7e8da3;font-size:.72rem;letter-spacing:.03em}
.cb{padding:12px 13px 13px}.src{font-size:.68rem;color:#f2c94c;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}
.addr{font-size:.96rem;font-weight:850;line-height:1.28;min-height:0;margin:6px 0 9px;color:#f6f8fb}'''
new_css='''.block-container{max-width:1560px;padding:.7rem 1rem 2rem!important}
.stApp{background:radial-gradient(circle at 15% -10%,#172236 0,#0b111b 35%,#080d14 72%);color:#f5f7fb}
.hero{display:flex;justify-content:space-between;align-items:center;gap:14px;background:linear-gradient(120deg,rgba(24,35,52,.97),rgba(11,18,29,.97));border:1px solid #2b3d57;border-radius:14px;padding:14px 17px;margin-bottom:8px;box-shadow:0 10px 30px rgba(0,0,0,.2)}
.brand{font-size:1.35rem;font-weight:950;letter-spacing:-.035em}.brand b{color:#f0c94a}.sub{font-size:.68rem;color:#98a9bf;margin-top:3px}
.badge{font-size:.64rem;border:1px solid #347d58;color:#b8f1cd;background:#10261c;border-radius:999px;padding:6px 9px;white-space:nowrap;font-weight:800}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.card{background:linear-gradient(180deg,#131d2b,#101824);border:1px solid #273950;border-radius:11px;overflow:hidden;box-shadow:0 5px 16px rgba(0,0,0,.16);transition:transform .14s ease,border-color .14s ease,box-shadow .14s ease}
.card:hover{transform:translateY(-2px);border-color:#526a8b;box-shadow:0 10px 22px rgba(0,0,0,.23)}
.preview{display:block;width:100%;height:155px;object-fit:cover;background:linear-gradient(135deg,#192638,#111925)}
.noimg{display:grid;place-items:center;color:#73839a;font-size:.66rem;letter-spacing:.03em}
.cb{padding:9px 10px 10px}.src{font-size:.58rem;color:#f0c94a;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}
.addr{font-size:.82rem;font-weight:850;line-height:1.25;min-height:2.05em;margin:4px 0 7px;color:#f7f9fc}'''
if old_css not in s:
    raise SystemExit('CSS anchor not found')
s=s.replace(old_css,new_css,1)

s=s.replace('.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:5px}', '.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:4px}',1)
s=s.replace('padding:6px 8px;min-height:46px', 'padding:5px 7px;min-height:40px',1)
s=s.replace('.metric span{display:block;color:#91a0b4;font-size:.58rem', '.metric span{display:block;color:#91a0b4;font-size:.52rem',1)
s=s.replace('.metric b{font-size:.82rem', '.metric b{font-size:.74rem',1)
s=s.replace('@media(min-width:1500px){.block-container{max-width:1500px}.cards{gap:20px}.preview{height:235px}}', '@media(min-width:1700px){.block-container{max-width:1640px}.cards{grid-template-columns:repeat(5,minmax(0,1fr));gap:11px}.preview{height:160px}}',1)
s=s.replace('@media(max-width:1050px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:205px}}', '@media(max-width:1180px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}.preview{height:150px}}@media(max-width:820px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:132px}}',1)
s=s.replace('@media(max-width:650px){.block-container{padding:.38rem .42rem 1.25rem!important}.hero{padding:11px 10px}', '@media(max-width:650px){.block-container{padding:.3rem .34rem 1.1rem!important}.hero{padding:9px 9px}',1)
s=s.replace('.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.preview{height:108px}', '.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.preview{height:96px}',1)
s=s.replace('.cb{padding:6px 6px 7px}', '.cb{padding:5px 5px 6px}',1)
s=s.replace('.addr{font-size:.66rem;line-height:1.23;min-height:0;margin:3px 0 5px}', '.addr{font-size:.62rem;line-height:1.22;min-height:2.4em;margin:3px 0 4px}',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.27 patch applied successfully')
