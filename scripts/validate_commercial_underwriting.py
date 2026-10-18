"""Replay source-indexed cases through the shared pipeline, without paid AI.

The manifest contains catalogue fields and captured research records, not prose
or conclusions. This validates automatic interpretation/rendering from those
inputs. It does not certify automatic source discovery, extraction, private-pack
review, independent editorial approval or the customer purchase journey.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legal_pack_service import analyse_uploaded_pack
from acquisition_build import engine_identity
from acquisition_presentation import make_brief
from acquisition_premium import render_pdf, render_html
from acquisition_underwriting import underwriting_view
from pypdf import PdfReader


def run(manifest, output):
    output.mkdir(parents=True, exist_ok=True)
    results=[]
    for case in manifest:
        report=analyse_uploaded_pack(case['catalogue']['address'], [], case['catalogue'], research=case['research'])['acquisition']
        report['created_at']=case['as_of']
        assert 'written_assessment' not in report
        brief=make_brief(report)
        prefix=output/case['id']
        prefix.with_suffix('.json').write_text(json.dumps(report,indent=2))
        prefix.with_suffix('.pdf').write_bytes(render_pdf(report))
        prefix.with_suffix('.html').write_text(render_html(report))
        pdf=PdfReader(prefix.with_suffix('.pdf'))
        body='\n'.join(p.extract_text() for p in pdf.pages)
        failures=[]
        for expected in case.get('expect_text',[]):
            if expected not in body:failures.append('Missing: '+expected)
        for forbidden in case.get('reject_text',[]):
            if forbidden in body:failures.append('Unexpected: '+forbidden)
        if len(pdf.pages)!=1:failures.append('Snapshot exceeds one page')
        if brief['editorial_quality']['blockers']:failures.append('Editorial contract blocked')
        if report['investigation']['external_research'].get('rejected'):failures.append('Research rejected')
        results.append({'case':case['id'],'property':report['property'],'engine':engine_identity(),
            'input_sha256':hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest(),
            'pdf_sha256':hashlib.sha256(prefix.with_suffix('.pdf').read_bytes()).hexdigest(),
            'method':'Source-indexed public evidence through shared pipeline; no manual narrative or provider calls',
            'manual_inputs':'Source selection and catalogue/research indexing',
            'pages':len(pdf.pages),'failures':failures,'underwriting':underwriting_view(report),
            'provider_calls':0,'paid_approval':False,'full_pack_acceptance':False})
    (output/'validation.json').write_text(json.dumps(results,indent=2))
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();results=run(json.loads(a.manifest.read_text()),a.output)
    print(json.dumps([{k:r[k] for k in ('case','pages','failures')} for r in results],indent=2))
    raise SystemExit(any(r['failures'] for r in results))
