from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')

s=s.replace('BUILD = "V6.43-COMPACT-YIELD"','BUILD = "V6.44-ALIGNED-DETAILS"',1)

anchor='''/* V6.42 wider property photography */\n.previewLink{display:block!important;width:100%!important;margin:0!important;padding:0!important;overflow:hidden!important}'''
insert='''/* V6.44 harmonise card bottoms */\n.card{display:flex!important;flex-direction:column!important;height:100%!important}\n.cb{display:flex!important;flex-direction:column!important;flex:1 1 auto!important}\n.analysis{margin-top:auto!important}\n.cardActions{margin-top:9px!important}\n@media(max-width:650px){.card{display:flex!important;flex-direction:column!important}.cb{display:flex!important;flex-direction:column!important;flex:1 1 auto!important}.analysis{margin-top:auto!important}}\n\n/* V6.42 wider property photography */\n.previewLink{display:block!important;width:100%!important;margin:0!important;padding:0!important;overflow:hidden!important}'''
if anchor not in s:
    raise SystemExit('CSS anchor missing')
s=s.replace(anchor,insert,1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.44 bottom-aligned investment details applied')
