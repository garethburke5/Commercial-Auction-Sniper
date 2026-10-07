"""Commercial exports must preserve material content and the paid boundary."""
from io import BytesIO
from zipfile import ZipFile

import pytest

from acquisition_report import render, commercial_brief
from acquisition_document import render_docx
from acquisition_intelligence import build_acquisition, snapshot
from web_platform.tests.test_acquisition_workspace import model


def full_report():
    report = build_acquisition(model(), {'guide': 250000, 'rent': 35000})
    # Legacy stored reports still support their original export format. New
    # investigation reports ignore inserted commercial_brief narratives.
    report.pop('investigation')
    report['commercial_brief'] = {
        'as_of': '2026-10-07', 'status': 'Reviewed source specimen',
        'summary': 'A two-unit retail investment.', 'conclusion': 'Resolve the title plan before committing.',
        'key_figures': [{'label': 'Annual rent', 'value': '£35,000', 'basis': 'Lease p. 4'}],
        'income_rows': [{'unit': 'Shop', 'tenant': 'A & B', 'rent': '£35,000', 'terms': 'Five years', 'source': 'Lease p. 4'}],
        'income_commentary': ['The receipt ledger does not prove current arrears clearance.'],
        'cost_rows': [{'item': 'Fixed fees', 'amount': '£3,300', 'basis': 'Conditions p. 2'}],
        'sensitivity_rows': [{'scenario': 'Void', 'rent': '£0', 'yield': '0%', 'meaning': 'Before holding costs'}],
        'risks': [{'priority': 'High', 'title': f'Material risk {i}', 'finding': f'Fact {i}', 'action': f'Check {i}', 'source': 'Title p. 1'} for i in range(8)],
        'checks': [{'who': 'Solicitor', 'action': 'Obtain the plan', 'source': 'Title p. 1'}],
        'source_notes': ['The report reviews the stated pack only.'], 'scope': 'Acquisition research.'}
    return report


def test_compact_html_preserves_all_risks_and_separates_print_evidence():
    report = full_report()
    html = render(report, standalone=True)
    assert html.count('<section class="acq-page"') == 5
    assert '<details class="acq-appendix">' in html
    assert '.acq-appendix{display:none!important}' in html
    assert 'Material risk 7' in html
    assert 'A &amp; B' in html
    assert 'The receipt ledger does not prove' in html
    report['commercial_brief']['summary'] = '<script>not executable</script>'
    assert '<script>not executable' not in render(report)
    assert '&lt;script&gt;not executable' in render(report)


def test_docx_preserves_material_risks_and_uses_five_page_groups():
    with ZipFile(BytesIO(render_docx(full_report()))) as archive:
        xml = archive.read('word/document.xml').decode()
        styles = archive.read('word/styles.xml').decode()
    assert xml.count('<w:pageBreakBefore') == 4
    assert 'w:type="page"' not in xml  # Empty break paragraphs can create blank overflow pages.
    assert 'Material risk 7' in xml and 'Fact 7' in xml and 'Check 7' in xml
    assert 'Annual rent' in xml and '£35,000' in xml
    assert 'w:tblHeader' in xml and 'D9D9D9' in xml
    assert 'Title' in styles


def test_snapshot_cannot_access_the_commercial_export_even_if_accidentally_attached():
    report = full_report()
    free = snapshot(report)
    # Defence in depth: renderer ignores an accidentally attached paid projection.
    free['commercial_brief'] = report['commercial_brief']
    assert 'Material risk 7' not in render(free)
    with pytest.raises(ValueError):
        render_docx(free)
    with pytest.raises(ValueError):
        commercial_brief(free)


def test_generic_full_report_retains_unquantified_risks():
    report = build_acquisition(model(), {'guide': 250000, 'rent': 35000})
    brief = commercial_brief(report)
    assert any('arrears' in r['title'].lower() for r in brief['risks'])
    assert any('£3,300' == r['amount'] for r in brief['cost_rows'])
    assert all('approved' not in str(value).lower() for value in brief.values())


def test_generic_report_preserves_catalogue_basis_lease_nuance_and_terminal_status():
    report = build_acquisition(model(), {'guide': 250000, 'rent': 35000})
    report.update(listing_status='SOLD', auction_date='2026-10-07', catalogue_as_of='2026-10-07T15:00:00Z',
                  tenancy_schedule=[{'Address': 'Ground floor', 'Present Lessee': 'Trading name',
                                     'Current Rent (PA)': '£35,000', 'Lease Details': 'Five years'}],
                  lease_details=[{'document': 'Executed Lease.pdf', 'tenant': 'Legal person',
                                  'evidence': [{'document': 'Executed Lease.pdf', 'page': 4}],
                                  'breaks': [{'party': 'Tenant', 'date_raw': '7 October 2028',
                                              'notice_raw': 'not less than six months', 'evidence': []}],
                                  'reviews': [{'text': 'Annual CPI', 'evidence': []}],
                                  'repairs': [{'text': 'Scoped repairing covenant', 'evidence': []}],
                                  'repair_basis': 'Retained structure and recovery require confirmation',
                                  'security': {'position': 'LTA 1954 excluded',
                                               'action': 'Check warning notice and declaration', 'evidence': []}}])
    brief = commercial_brief(report)
    assert brief['status'].startswith('SOLD')
    assert 'does not establish a currently available purchase' in brief['summary']
    assert brief['income_rows'][0]['tenant'] == 'Published: Trading name'
    assert '2026-10-07' in brief['income_rows'][0]['source']
    comments = ' '.join(brief['income_commentary'])
    assert 'Legal person' in comments and '7 October 2028' in comments
    assert 'six months' in comments and 'Annual CPI' in comments
    assert 'Retained structure' in comments and 'warning notice' in comments
