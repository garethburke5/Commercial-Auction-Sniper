from pathlib import Path
import py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=s.replace('BUILD = "V6.52-SOURCES-FILTERS-IMAGES"','BUILD = "V6.53-PRIORITY-SOURCE-BOOT"',1)
anchor='''rows,health,updated=load_rows()
st.markdown('''
insert='''@st.cache_data(ttl=21600,show_spinner=False)
def _v653_priority_boot_rows():
    jobs={
        "Pattinson":_pattinson_current,
        "Clive Emson":_clive_emson_current,
        "Strettons":_strettons_current,
        "Acuitus":_acuitus_current,
    }
    out=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs={ex.submit(fn):src for src,fn in jobs.items()}
        for f in as_completed(futs):
            try:
                out.extend(f.result() or [])
            except Exception:
                pass
    return _clean_rows(out)

rows,health,updated=load_rows()
try:
    priority=_v653_priority_boot_rows()
    if priority:
        rows=_merge_property_universe(rows,priority)
except Exception:
    pass
st.markdown('''
if anchor not in s: raise SystemExit('rows load anchor missing')
s=s.replace(anchor,insert,1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.53 priority sources hydrate on app load')
