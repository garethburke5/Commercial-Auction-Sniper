from pathlib import Path
import re, py_compile
p=Path('app.py')
s=p.read_text(encoding='utf-8')
s=re.sub(r'BUILD = "V6\.\d+[^"\n]*"','BUILD = "V6.39-ALIGNED-YIELD"',s,count=1)
old='''with tool_yield:\n    target_yield=st.number_input("Target yield (%)",min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",help="Change this to recalculate the maximum purchase price for every rented property")'''
new='''with tool_yield:\n    target_yield=st.number_input("Target yield (%)",min_value=1.0,max_value=30.0,value=10.0,step=.5,format="%.1f",help="Target yield — changes the max purchase price on every rented property",label_visibility="collapsed")'''
if old not in s: raise SystemExit('target yield input anchor missing')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
py_compile.compile(str(p),doraise=True)
print('V6.39 yield control aligned with toolbar buttons')
