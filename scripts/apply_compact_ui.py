from pathlib import Path

p=Path('app.py')
s=p.read_text(encoding='utf-8')

repls={
'''BUILD = "V6.24-STRETTONS-EXACT-BOOT"''':'''BUILD = "V6.25-COMPACT-UI"''',
'''def money(v): return "Unknown" if v is None else f"£{v:,.0f}"\ndef pct(v): return "Unknown" if v is None else f"{v:.1f}%"''':'''def money(v): return "—" if v is None else f"£{v:,.0f}"\ndef pct(v): return "—" if v is None else f"{v:.1f}%"''',
'''else '<div class="preview noimg">IMAGE NOT YET INDEXED</div>')''':'''else '<div class="preview noimg">Photo unavailable</div>')''',
'''.cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}''':''' .cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}''',
'''.card{background:#121b29;border:1px solid #2b3a50;border-radius:14px;overflow:hidden;box-shadow:0 6px 20px rgba(0,0,0,.18);transition:transform .15s ease,border-color .15s ease}''':'''.card{background:#121b29;border:1px solid #26364b;border-radius:12px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,.14);transition:transform .15s ease,border-color .15s ease}''',
'''.cb{padding:15px 16px 16px}.src{font-size:.72rem;color:#f2c94c;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}''':'''.cb{padding:12px 13px 13px}.src{font-size:.68rem;color:#f2c94c;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}''',
'''.addr{font-size:1rem;font-weight:850;line-height:1.32;min-height:2.65em;margin:7px 0 13px;color:#f6f8fb}''':'''.addr{font-size:.96rem;font-weight:850;line-height:1.28;min-height:0;margin:6px 0 9px;color:#f6f8fb}''',
'''.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.sizeMetric{grid-column:span 2}.metric{background:#182333;border:1px solid #202d40;border-radius:8px;padding:9px 10px}''':'''.metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:5px}.sizeMetric{grid-column:span 2}.metric{background:#162130;border:1px solid #223047;border-radius:7px;padding:6px 8px;min-height:46px;display:flex;flex-direction:column;justify-content:center}''',
'''.metric span{display:block;color:#91a0b4;font-size:.64rem;margin-bottom:3px}.metric b{font-size:.88rem;color:#fff}''':'''.metric span{display:block;color:#91a0b4;font-size:.58rem;margin-bottom:1px;line-height:1.15}.metric b{font-size:.82rem;line-height:1.15;color:#fff}''',
'''.meta{font-size:.66rem;color:#aab6c7;margin-top:10px;line-height:1.4;min-height:1.4em}''':'''.meta{font-size:.62rem;color:#9faec1;margin-top:7px;line-height:1.3;min-height:0}''',
'''.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:10px}''':'''.chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:7px}''',
'''.analysis{margin-top:9px;border-top:1px solid #26354a;padding-top:8px}''':'''.analysis{margin-top:7px;border-top:1px solid #26354a;padding-top:6px}''',
'''.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:8px;padding:10px 8px;margin-top:11px;font-size:.76rem;font-weight:950}''':'''.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:7px;padding:8px 7px;margin-top:8px;font-size:.72rem;font-weight:900}''',
'''@media(max-width:650px){.block-container{padding:.45rem .5rem 1.5rem!important}.hero{padding:13px 12px}.brand{font-size:1.1rem}.sub{font-size:.58rem}.badge{font-size:.55rem;padding:5px 7px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.preview{height:112px}.cb{padding:7px}.src{font-size:.47rem}.addr{font-size:.68rem;min-height:2.7em;margin:4px 0 7px}.metrics{gap:3px}.metric{padding:5px}.metric span{font-size:.40rem}.metric b{font-size:.58rem}.meta{font-size:.42rem;margin-top:5px}.action{font-size:.50rem;padding:6px;margin-top:6px}}''':'''@media(max-width:650px){.block-container{padding:.38rem .42rem 1.25rem!important}.hero{padding:11px 10px}.brand{font-size:1.05rem}.sub{font-size:.56rem}.badge{font-size:.53rem;padding:4px 6px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.preview{height:108px}.cb{padding:6px 6px 7px}.src{font-size:.45rem}.addr{font-size:.66rem;line-height:1.23;min-height:0;margin:3px 0 5px}.metrics{gap:3px}.metric{padding:3px 5px;min-height:36px;border-radius:6px}.metric span{font-size:.38rem;margin-bottom:0}.metric b{font-size:.56rem;line-height:1.1}.meta{font-size:.40rem;margin-top:4px;min-height:0}.chips{margin-top:5px;gap:3px}.chip{font-size:.48rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.58rem}.action{font-size:.48rem;padding:5px 4px;margin-top:5px;border-radius:6px}}'''
}
for old,new in repls.items():
    if old not in s:
        raise SystemExit(f'missing patch target: {old[:80]!r}')
    s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
