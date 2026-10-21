"""Render retained evidence through the customer renderer without provider calls.

This verifies presentation, not renewed source capture, original-file hashes or
independent source review. Inputs/outputs can contain private pack material.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acquisition_build import engine_identity
from acquisition_presentation import make_brief
from acquisition_premium import render_pdf, render_html
from acquisition_quality import evidence_sufficiency
from pypdf import PdfReader


def render_validation(report, prefix, source_digest):
    prefix = Path(prefix); prefix.parent.mkdir(parents=True, exist_ok=True)
    report = dict(report)
    if report.get('report_media') and not Path(report['report_media'].get('photo_path', '')).is_file():
        report.pop('report_media')
    brief = make_brief(report)
    page_map = []
    prefix.with_suffix('.pdf').write_bytes(render_pdf(report, page_map=page_map))
    prefix.with_suffix('.html').write_text(render_html(report))
    pdf = PdfReader(prefix.with_suffix('.pdf'))
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    expected = len(brief['pages']) + len(brief['appendix_pages'])
    appendix_start = next((p['page'] for p in page_map if p['appendix']), len(pdf.pages)+1)
    main_pages = appendix_start-1
    failures = []
    if (brief['product_outcome'] == 'free_snapshot' and len(pdf.pages) > 1) or (brief['product_outcome']=='insufficient_evidence' and len(pdf.pages)>3) or (brief['product_outcome']=='review_required' and (main_pages > 5 or main_pages != len(brief['pages']))):
        failures.append(f'Rendered {len(pdf.pages)} pages; planned {expected}. Inspect overflow.')
    if any(x in text.casefold() for x in ('march april', '2march', '1march')):
        failures.append('Malformed amended date leaked into the customer PDF.')
    failures.extend('Editorial: '+x['code'] for x in brief['editorial_quality']['blockers'])
    result = {'engine': engine_identity(), 'input_sha256': source_digest,
              'method': 'Retained evidence presentation replay; no source re-extraction or provider calls',
              'property': report['property'], 'main_pages': len(brief['pages']), 'actual_pages': len(pdf.pages),
              'actual_main_pages': main_pages, 'actual_appendix_pages': len(pdf.pages)-main_pages,
              'section_pages': page_map,
              'chart_types': [b['chart'] for p in brief['pages'] for b in p['blocks'] if b['kind']=='chart'],
              'evidence_eligibility': evidence_sufficiency(report), 'editorial_quality': brief['editorial_quality'], 'failures': failures,
              'paid_release_approved': False, 'provider_calls': 0}
    prefix.with_suffix('.validation.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-json', type=Path, required=True)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    raw = args.report_json.read_bytes()
    result = render_validation(json.loads(raw), args.output_prefix, hashlib.sha256(raw).hexdigest())
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['failures']))
