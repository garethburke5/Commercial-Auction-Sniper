from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
# Build marker.
for old in ('BUILD = "V6.30-FAST-SCAN-GRID"','BUILD = "V6.31-OCCUPANCY"','BUILD = "V6.32-SHARP-SCAN"'):
    if old in s:
        s=s.replace(old,'BUILD = "V6.33-CLICKABLE-IMAGES"',1)
        break
# Wrap preview image in exact property URL. Escape both URL and image.
old='''        preview=(f'<img class="preview" src="{html.escape(x["image"])}" loading="lazy">' if x.get("image")
                 else '<div class="preview noimg">Photo unavailable</div>')'''
new='''        _property_url=html.escape(str(x.get("url") or ""),quote=True)
        preview=(f'<a class="previewLink" href="{_property_url}" target="_blank" rel="noopener noreferrer" aria-label="Open property details"><img class="preview" src="{html.escape(x["image"],quote=True)}" loading="lazy"></a>' if x.get("image") and _property_url
                 else (f'<img class="preview" src="{html.escape(x["image"],quote=True)}" loading="lazy">' if x.get("image") else '<div class="preview noimg">Photo unavailable</div>'))'''
if old not in s:
    raise SystemExit('preview anchor missing')
s=s.replace(old,new,1)
css='''.previewLink{display:block;text-decoration:none!important;cursor:pointer}.previewLink .preview{transition:filter .12s ease,transform .12s ease}.previewLink:hover .preview{filter:brightness(1.06)}\n'''
s=s.replace('</style>\n""",unsafe_allow_html=True)',css+'</style>\n""",unsafe_allow_html=True)',1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.33 clickable property images applied')
