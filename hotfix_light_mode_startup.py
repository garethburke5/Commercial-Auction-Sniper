from pathlib import Path
p=Path('app.py')
s=p.read_text()
needle='if LIGHT_MODE:\n    st.markdown("""\n'
replacement='LIGHT_MODE = bool(st.session_state.get("light_mode", False))\n\nif LIGHT_MODE:\n    st.markdown("""\n'
if needle not in s:
    raise SystemExit('LIGHT_MODE insertion point not found')
s=s.replace(needle,replacement,1)
p.write_text(s)
print('patched LIGHT_MODE startup state')
