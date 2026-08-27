from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.29-READABILITY"','BUILD = "V6.30-FAST-SCAN-GRID"',1)

old='''@media(max-width:650px){.block-container{padding:.38rem .45rem 1.2rem!important}.hero{padding:10px 11px;margin-bottom:7px}.brand{font-size:1.08rem}.sub{font-size:.58rem}.badge{font-size:.56rem;padding:5px 7px}.cards{grid-template-columns:1fr;gap:8px}.card{display:grid;grid-template-columns:118px minmax(0,1fr);align-items:stretch}.preview{height:100%;min-height:178px;border-radius:0;object-fit:cover}.cb{padding:9px 9px 9px}.src{font-size:.57rem}.addr{font-size:.78rem;line-height:1.25;min-height:0;margin:4px 0 7px}.metrics{gap:3px}.metric{padding:4px 6px;min-height:36px;border-radius:6px}.metric span{font-size:.49rem;margin-bottom:1px}.metric b{font-size:.67rem;line-height:1.12}.meta{font-size:.52rem;margin-top:5px;line-height:1.3}.chips{margin-top:5px;gap:3px}.chip{font-size:.52rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.61rem}.action{font-size:.61rem;padding:7px 5px;margin-top:6px;border-radius:6px}.factgrid{grid-template-columns:1fr}.research{gap:4px}.iread{padding:6px 7px}}'''
new='''@media(max-width:650px){.block-container{padding:.34rem .38rem 1.15rem!important}.hero{padding:9px 10px;margin-bottom:6px}.brand{font-size:1.05rem}.sub{font-size:.56rem}.badge{font-size:.54rem;padding:4px 6px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.card{display:block}.preview{height:112px;min-height:0;border-radius:0;object-fit:cover}.cb{padding:7px 7px 8px}.src{font-size:.52rem}.addr{font-size:.70rem;line-height:1.23;min-height:3.35em;margin:4px 0 6px}.metrics{gap:3px}.metric{padding:4px 5px;min-height:38px;border-radius:6px}.metric span{font-size:.44rem;margin-bottom:1px}.metric b{font-size:.62rem;line-height:1.12}.meta{font-size:.47rem;margin-top:5px;line-height:1.25}.chips{margin-top:5px;gap:3px}.chip{font-size:.47rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.56rem}.action{font-size:.55rem;padding:6px 4px;margin-top:6px;border-radius:6px}.factgrid{grid-template-columns:1fr}.research{gap:4px}.iread{padding:6px 7px}}'''
if old not in s:
    raise SystemExit('V6.29 mobile layout anchor not found')
s=s.replace(old,new,1)

# Slightly reduce desktop card bulk while retaining V6.29 readability improvements.
s=s.replace('.preview{display:block;width:100%;height:172px;', '.preview{display:block;width:100%;height:162px;',1)
s=s.replace('.cb{padding:11px 12px 12px}', '.cb{padding:10px 11px 11px}',1)
s=s.replace('.addr{font-size:.94rem;', '.addr{font-size:.90rem;',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.30 fast-scan grid applied')
