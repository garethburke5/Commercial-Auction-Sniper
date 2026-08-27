from pathlib import Path
import py_compile

p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.28-IMAGE-REPAIR"','BUILD = "V6.29-READABILITY"',1)

repls={
'.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}':'.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}',
'.preview{display:block;width:100%;height:155px;object-fit:cover;background:linear-gradient(135deg,#192638,#111925)}':'.preview{display:block;width:100%;height:172px;object-fit:cover;background:linear-gradient(135deg,#192638,#111925)}',
'.cb{padding:9px 10px 10px}.src{font-size:.58rem;color:#f0c94a;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none}':'.cb{padding:11px 12px 12px}.src{font-size:.66rem;color:#f5d45e;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:none;letter-spacing:.01em}',
'.addr{font-size:.82rem;font-weight:850;line-height:1.25;min-height:2.05em;margin:4px 0 7px;color:#f7f9fc}':'.addr{font-size:.94rem;font-weight:850;line-height:1.28;min-height:2.45em;margin:5px 0 9px;color:#ffffff}',
'.metric span{display:block;color:#91a0b4;font-size:.52rem;margin-bottom:1px;line-height:1.15}.metric b{font-size:.74rem;line-height:1.15;color:#fff}':'.metric span{display:block;color:#aebbd0;font-size:.61rem;margin-bottom:2px;line-height:1.15;font-weight:650}.metric b{font-size:.86rem;line-height:1.16;color:#fff;font-weight:850}',
'.meta{font-size:.62rem;color:#9faec1;margin-top:7px;line-height:1.3;min-height:0}':'.meta{font-size:.68rem;color:#b0bdd0;margin-top:8px;line-height:1.35;min-height:0}',
'.chip{font-size:.61rem;font-weight:850;padding:4px 7px;border-radius:999px;background:#223047;border:1px solid #354966;color:#dce7f5}':'.chip{font-size:.66rem;font-weight:800;padding:4px 7px;border-radius:999px;background:#223047;border:1px solid #405674;color:#e7eef8}',
'.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:7px;padding:8px 7px;margin-top:8px;font-size:.72rem;font-weight:900}':'.action{display:block;text-align:center;text-decoration:none!important;background:#f2c94c;color:#171208!important;border-radius:8px;padding:9px 8px;margin-top:9px;font-size:.77rem;font-weight:950}',
'@media(max-width:1180px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}.preview{height:150px}}@media(max-width:820px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:132px}}':'@media(max-width:1180px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}.preview{height:165px}}@media(max-width:820px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.preview{height:155px}.addr{font-size:.9rem}}',
'@media(max-width:650px){.block-container{padding:.3rem .34rem 1.1rem!important}.hero{padding:9px 9px}.brand{font-size:1.05rem}.sub{font-size:.56rem}.badge{font-size:.53rem;padding:4px 6px}.cards{grid-template-columns:repeat(2,minmax(0,1fr));gap:5px}.preview{height:96px}.cb{padding:5px 5px 6px}.src{font-size:.45rem}.addr{font-size:.62rem;line-height:1.22;min-height:2.4em;margin:3px 0 4px}.metrics{gap:3px}.metric{padding:3px 5px;min-height:36px;border-radius:6px}.metric span{font-size:.38rem;margin-bottom:0}.metric b{font-size:.56rem;line-height:1.1}.meta{font-size:.40rem;margin-top:4px;min-height:0}.chips{margin-top:5px;gap:3px}.chip{font-size:.48rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.58rem}.action{font-size:.48rem;padding:5px 4px;margin-top:5px;border-radius:6px}}':'@media(max-width:650px){.block-container{padding:.38rem .45rem 1.2rem!important}.hero{padding:10px 11px;margin-bottom:7px}.brand{font-size:1.08rem}.sub{font-size:.58rem}.badge{font-size:.56rem;padding:5px 7px}.cards{grid-template-columns:1fr;gap:8px}.card{display:grid;grid-template-columns:118px minmax(0,1fr);align-items:stretch}.preview{height:100%;min-height:178px;border-radius:0;object-fit:cover}.cb{padding:9px 9px 9px}.src{font-size:.57rem}.addr{font-size:.78rem;line-height:1.25;min-height:0;margin:4px 0 7px}.metrics{gap:3px}.metric{padding:4px 6px;min-height:36px;border-radius:6px}.metric span{font-size:.49rem;margin-bottom:1px}.metric b{font-size:.67rem;line-height:1.12}.meta{font-size:.52rem;margin-top:5px;line-height:1.3}.chips{margin-top:5px;gap:3px}.chip{font-size:.52rem;padding:3px 5px}.analysis{margin-top:5px;padding-top:5px}.analysis summary{font-size:.61rem}.action{font-size:.61rem;padding:7px 5px;margin-top:6px;border-radius:6px}.factgrid{grid-template-columns:1fr}.research{gap:4px}.iread{padding:6px 7px}}'
}
for old,new in repls.items():
    if old not in s:
        raise SystemExit('UI anchor missing: '+old[:70])
    s=s.replace(old,new,1)

# Improve card hierarchy: make GIY visually prominent without adding clutter.
s=s.replace('<div class="metric"><span>GIY</span><b>{pct(y)}</b></div>', '<div class="metric yieldMetric"><span>GIY</span><b>{pct(y)}</b></div>',1)
# append targeted CSS before closing style
s=s.replace('</style>\n""",unsafe_allow_html=True)', '.yieldMetric{background:#14271f;border-color:#2e5a45}.yieldMetric b{color:#b9f3cf}\n</style>\n""",unsafe_allow_html=True)',1)

p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.29 readability UI patch applied')
