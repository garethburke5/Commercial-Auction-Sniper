"""Replay retained evidence through the real report code, with zero API calls.

Inputs remain private. SHA-256 checks bind cached OCR to the original files.
No review completion, current source refresh or product approval is invented.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legal_pack_engine import PackDocument, DocType
from legal_pack_ingest import IngestResult, IngestAsset, IngestIssue
from legal_pack_review import build_evidence_report
from acquisition_transcription import apply_transcriptions
from acquisition_pipeline import investigate_acquisition, evidence_scope
from acquisition_premium import render_pdf, render_html
from acquisition_build import engine_identity
from acquisition_evidence_graph import reasoning_packet, norm


def replay(bundle, originals, catalogue, research, corrections=(), visual=(), notes=None):
    documents=[]; seen=set()
    for cached in bundle['ingestion']['documents']:
        raw=(originals/cached['name']).read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if digest!=cached['sha256']:
            raise ValueError('Original does not match cached extraction: '+cached['name'])
        if digest in seen:
            continue
        seen.add(digest)
        meta=copy.deepcopy(cached['metadata'])
        documents.append(PackDocument(cached['name'],DocType(cached['type']),
                         '\n\n'.join(p.get('text','') for p in meta['pages']),digest,meta))
    documents=apply_transcriptions(documents,corrections)
    ingestion=IngestResult(documents=documents,
        assets=[IngestAsset(**a) for a in bundle['ingestion']['assets']],
        issues=[IngestIssue(**i) for i in bundle['ingestion']['issues']],
        total_pages=sum(len(d.metadata['pages']) for d in documents))
    cat=copy.deepcopy(catalogue);cat['visual_dispositions']=visual
    model=build_evidence_report(cat['address'],documents,ingestion,cat)
    model['engine']=engine_identity()
    model['source_pages']=[{'document':d.name,'document_sha256':d.sha256,
                           'page':p['page'],'text':p.get('text',''),'ocr':p.get('ocr',False)}
                          for d in documents for p in d.metadata['pages']]
    model['evidence_scope']=evidence_scope([(d.name,b'') for d in documents],documents)
    report=investigate_acquisition(model,cat,research=research)
    if notes:
        packet=reasoning_packet(report,report['investigation']);reviewed=set();findings=[]
        for note in notes['findings']:
            finding={k:v for k,v in note.items() if k!='evidence'};ids=[]
            for citation in note['evidence']:
                matches=[s for s in packet['sources'] if s.get('source_kind')=='legal_pack'
                         and s.get('document')==citation['document'] and s.get('page')==citation['page']
                         and norm(citation['excerpt']) in norm(s.get('text',''))]
                if len(matches)!=1:raise ValueError('Analyst observation does not match one source page')
                ids.append(matches[0]['id'])
            finding['evidence_ids']=ids;reviewed.update(ids);findings.append(finding)
        review={'reviewer':notes['reviewer'],'evidence_digest':packet['evidence_digest'],
                'reviewed_source_ids':sorted(reviewed),
                'unreviewed_source_ids':sorted({s['id'] for s in packet['sources']}-reviewed),
                'findings':findings,'research_requests':[],
                'limitations':['Targeted analyst observations only. Other source pages are not marked reviewed.']}
        report=investigate_acquisition(model,cat,research=research,open_review=review)
        if not report['investigation']['open_review']['provenance_valid']:
            raise ValueError('Analyst review failed provenance validation')
    report['benchmark']={'method':'Cached extraction replay; original hashes verified; no paid provider',
        'scope_note':'Owner-review benchmark: rebuilt from the retained legal pack and dated public evidence. '
                     'Selected material clauses were checked against the originals. This is not a fresh automated report or a complete professional due-diligence sign-off.'}
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--originals',type=Path,required=True);p.add_argument('--catalogue',type=Path,required=True)
    p.add_argument('--research',type=Path,required=True);p.add_argument('--corrections',type=Path)
    p.add_argument('--visual',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--notes',type=Path);p.add_argument('--photo',type=Path)
    args=p.parse_args();load=lambda path:json.loads(path.read_text()) if path else []
    catalogue=load(args.catalogue);research=load(args.research)
    full=replay(load(args.bundle),args.originals,catalogue,research,load(args.corrections),load(args.visual),load(args.notes))
    # The no-pack case starts with an empty document model. It never inherits
    # lease-only findings, private rent splits, or the with-pack conclusion.
    empty=build_evidence_report(catalogue['address'],[],IngestResult(),catalogue)
    empty['engine']=engine_identity()
    empty['evidence_scope']=evidence_scope([],[])
    public=investigate_acquisition(empty,catalogue,research=research)
    public['benchmark']={'method':'Public-evidence-only replay; no legal-pack facts supplied',
        'scope_note':'Owner-review benchmark using dated public evidence only. No legal pack was analysed for this version; advertised income, lease obligations and title extent remain unverified.'}
    args.output.mkdir(parents=True,exist_ok=True)
    for stem,report in [('Newbury_Investment_Report',full),('Newbury_Without_Legal_Pack',public)]:
        if args.photo:
            report['report_media']={'photo_path':str(args.photo),
                'photo_credit':'Retained auction catalogue photograph. Indicative appearance; not a title or condition survey.'}
        (args.output/(stem+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
        (args.output/(stem+'.pdf')).write_bytes(render_pdf(report))
        (args.output/(stem+'.html')).write_text(render_html(report))
    print(json.dumps({'with_pack_pages':full['coverage']['pages'],
                      'with_pack_income_reconciled':full['investigation']['income_reconciled'],
                      'without_pack_income_reconciled':public['investigation']['income_reconciled'],
                      'provider_calls':0,'paid_reports_available':False}))


if __name__=='__main__':main()
