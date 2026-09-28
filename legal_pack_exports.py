"""Browser-local report exports, independent of expiring server media URLs."""
import json
from legal_pack_report import render_review_html

def render_report_exports(model):
    payload=json.dumps({'id':model['report_id'],'html':render_review_html(model,standalone=True),'json':json.dumps(model,ensure_ascii=False,indent=2)},ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;font:14px/1.4 Arial,sans-serif;background:transparent;color:#183149}.exports{display:flex;gap:10px;flex-wrap:wrap}a{display:inline-block;background:#fff;border:1px solid #94a7b6;border-radius:7px;color:#183149;text-decoration:none;padding:11px 14px;font-weight:600}a:hover,a:focus{border-color:#00665f;background:#eef8f5;outline-color:#00665f}@media(max-width:560px){a{display:block;flex:1 1 100%;text-align:center}}</style></head><body><div class="exports"><a id="readable">Download readable report (HTML)</a><a id="saved">Save report to reopen (JSON)</a></div><script>
const report='''+payload+''';
for(const [id,kind,mime] of [['readable','html','text/html;charset=utf-8'],['saved','json','application/json']]){
 const link=document.getElementById(id);link.href=URL.createObjectURL(new Blob([report[kind]],{type:mime}));link.download='auction-sniper-'+report.id+'.'+kind;
}
</script></body></html>'''
