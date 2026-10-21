from copy import deepcopy

import pytest

from acquisition_intelligence import build_acquisition
from acquisition_interpretation import interpret
from acquisition_investigation import _scope_matches
from acquisition_narrative import writing_packet
from acquisition_presentation import make_brief
from acquisition_unit_schedule import income_schedule, energy_schedule
from test_acquisition_investigation import model, cat, external
from test_acquisition_narrative import draft


def multi_let():
    m = model()
    original = m['lease_details'][0]
    m['lease_details'] = []
    for label, rent, reversion in [('Main shop', 20000, False), ('Side shop', 6500, False),
                                    ('First-floor flat', 100, True), ('Second-floor flat', 100, True)]:
        lease = deepcopy(original)
        lease.update(document=label+'.pdf', demise=label, annual_rent=rent,
                     interest='Residential long lease' if reversion else 'Occupational lease / confirm interest')
        lease['evidence'] = [{'document': lease['document'], 'page': 1, 'excerpt': f'Annual rent £{rent:,}'}]
        m['lease_details'].append(lease)
    c = cat()
    c['rent'] = 26700
    return build_acquisition(m, c)


def test_every_income_source_reaches_rendered_report_even_if_writer_omits_figures():
    r = multi_let()
    r['written_assessment'] = draft(writing_packet(r))
    brief = make_brief(r)
    tables = [b for p in brief['pages'] for b in p['blocks']
              if b.get('kind') == 'table' and b.get('role') == 'income_schedule']
    assert len(tables) == 1
    rows = tables[0]['rows']
    assert [x[2] for x in rows] == ['£20,000', '£6,500', '£100', '£100', '£26,700']
    assert rows[0][3] == '74.9%'
    assert all('Ground rent' in x[1] for x in rows[2:4])
    assert {x['document'] for x in brief['references']} >= {d['document'] for d in r['investigation']['demises']}
    assert not any(b['kind'] == 'evidence' for p in brief['pages'] for b in p['blocks'])


@pytest.mark.parametrize('fault', ['missing_rent', 'duplicate_unit', 'unidentified_unit', 'unreconciled', 'wrong_total', 'no_evidence'])
def test_unresolved_lease_records_never_gain_an_invented_total_or_share(fault):
    r = multi_let()
    ds = r['investigation']['demises']
    if fault == 'missing_rent': ds[-1]['annual_rent'] = None
    if fault == 'duplicate_unit': ds[-1]['label'] = ds[0]['label']
    if fault == 'unidentified_unit': ds[-1]['demise_identified'] = False
    if fault == 'unreconciled': r['investigation']['income_reconciled'] = False
    if fault == 'wrong_total': r['rent'] = 30000
    if fault == 'no_evidence': ds[-1]['evidence'] = []
    s = income_schedule(r)
    assert not s['reconciled'] and s['total'] is None
    assert all(row['share_pct'] is None for row in s['rows'])
    assert 'not been added together' in s['explanation']
    if fault == 'missing_rent':
        assert s['rows'][-1]['annual_rent'] is None
        assert '£100 a year in ground rent' not in interpret(r)['ownership']


def test_public_pathway_cannot_receive_private_schedules():
    r = multi_let()
    r['evidence_scope'] = {'legal_pack_supplied': False}
    assert income_schedule(r)['rows'] == []
    assert energy_schedule(r) == []
    assert not {'unit-income-schedule', 'unit-energy-schedule'} & {f['id'] for f in writing_packet(r)['facts']}


def test_epc_schedule_distinguishes_two_units_and_preserves_address_discrepancy():
    r = multi_let()
    ds = r['investigation']['demises']
    ds[1]['epc'] = {'rating': 'D', 'valid_until': '2033-03-20', 'address': 'Side shop, EX1 1AB',
        'scope_note': 'Street and unit match; postcode differs from the auction particulars.',
        'source': {'document': 'EPC.pdf', 'page': 1, 'excerpt': 'Energy rating D'}}
    rows = energy_schedule(r)
    assert len(rows) == 2
    assert rows[0]['unit'] == 'Main shop' and not rows[0]['matched']
    assert rows[1]['unit'] == 'Side shop' and rows[1]['matched']
    assert 'rating D; valid until 20 March 2033' in rows[1]['position']
    assert 'postcode differs' in rows[1]['detail']
    r['written_assessment'] = draft(writing_packet(r))
    brief = make_brief(r)
    property_page = brief['pages'][2]
    table = next(b for b in property_page['blocks'] if b.get('kind') == 'table')
    assert table['rows'][0] == ['Main shop', 'No matching EPC identified']
    assert any(ref['document'] == 'EPC.pdf' for ref in brief['references'])
    r.pop('written_assessment')
    fallback = make_brief(r)
    assert not any(b.get('kind') == 'h' and b.get('text', '').startswith('Energy requirements for')
                   for p in fallback['appendix_pages'] for b in p['blocks'])


@pytest.mark.parametrize('subject', ['11 Main Street, Town', '1-3 Main Street, Town',
    'Flat above 1 Main Street, Town', '1 Main Street rear shop, Town', '1 Main Street/2 Side Road'])
def test_implicit_epc_matching_does_not_join_different_addresses_or_extents(subject):
    assert not _scope_matches({'subject': subject}, {'label': '1 Main Street'})


def test_explicit_association_and_exact_address_work_without_substring_matching():
    assert _scope_matches({'subject': '1 Main Street, Town'}, {'label': '1 Main St'})
    assert _scope_matches({'demise_document': 'shop.pdf', 'subject': 'Certificate alias'}, {'document': 'shop.pdf'})
    assert not _scope_matches({'demise_document': 'other.pdf', 'subject': '1 Main Street'},
                              {'document': 'shop.pdf', 'label': '1 Main Street'})


def test_low_rated_certificate_is_explained_as_found_not_missing():
    r = build_acquisition(model(), cat(), research=external('epc_certificate',
        demise_document='Lease 1 Main Street.pdf', rating='F', valid_until='2033-01-01'))
    card = next(c for c in interpret(r)['cards'] if c['id'].startswith('epc-substandard'))
    assert 'rating of F' in card['body'] and '1 Main Street' in card['body']
    assert 'not established' not in card['body'] and 'supply the certificate' not in card['body']


def test_pdf_validation_counts_real_main_pages_separately_from_long_sources(tmp_path, monkeypatch):
    from scripts.render_report_validation import render_validation
    import acquisition_premium
    import scripts.render_report_validation as validation
    # A long appendix must not fail the five-page main-brief limit. A long
    # main section must fail even if the declared section count still says one.
    def brief(long_main=False):
        paragraph = {'kind': 'p', 'text': 'Source description with enough detail to require several lines. '*8}
        return {'pages': [{'title': 'Assessment', 'blocks': [paragraph]*(35 if long_main else 1)}],
                'appendix_pages': [{'title': 'Sources', 'blocks': [paragraph]*35}],
                'product_outcome': 'review_required', 'status': 'Review', 'references': [],
                'editorial_quality': {'blockers': []}}
    r = {'property': 'Example warehouse'}
    monkeypatch.setattr(validation, 'evidence_sufficiency', lambda r: {'charge_eligible': False})
    monkeypatch.setattr(validation, 'render_html', lambda r: '<html></html>')
    for long_main in (False, True):
        b = brief(long_main)
        monkeypatch.setattr(acquisition_premium, 'make_brief', lambda r: b)
        monkeypatch.setattr(validation, 'make_brief', lambda r: b)
        result = render_validation(r, tmp_path/str(long_main), 'fixture')
        assert result['actual_appendix_pages'] > 1
        assert bool(result['failures']) == long_main
        assert (result['actual_main_pages'] > 1) == long_main


@pytest.mark.parametrize('rent', [True, -100, float('inf'), float('nan')])
def test_invalid_rent_cannot_reconcile_current_income(rent):
    m = model(); m['lease_details'][0]['annual_rent'] = rent
    c = cat(); c['rent'] = rent
    # Test the investigation directly: malformed values must not establish
    # contractual income, regardless of matching catalogue and lease values.
    from acquisition_investigation import investigate
    r = dict(m, rent=rent, tenure='Freehold', guide=200000, costs=[])
    result = investigate(r, m, c)
    assert not result['income_reconciled']
