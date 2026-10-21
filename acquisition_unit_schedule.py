"""Customer unit schedules derived from the investigated evidence.

These views neither extract new facts nor infer that several lease documents
describe separate current lettings. Public snapshots never receive pack data.
"""
from datetime import date

from acquisition_financials import number, rounded


def _pack(report):
    return bool(report.get('evidence_scope', {}).get('legal_pack_supplied', report.get('documents')))


def income_schedule(report):
    inv = report.get('investigation', {})
    if not _pack(report):
        return {'rows': [], 'reconciled': False, 'total': None, 'explanation': ''}
    demises = [d for d in inv.get('demises', []) if d.get('document')]
    rows = []
    for d in demises:
        annual = d.get('annual_rent')
        rows.append({'unit': d.get('label') or 'Unit not identified',
                     'income_type': 'Ground rent — flat sold on a long lease' if d.get('residential_reversion') else 'Letting rent',
                     'annual_rent': annual if number(annual) else None,
                     'tenant': None if d.get('residential_reversion') else d.get('tenant'),
                     'share_pct': None, 'evidence': d.get('evidence', [])})
    total = report.get('rent')
    reconciled = bool(inv.get('income_reconciled') and rows and number(total)
        and all(d.get('evidence') and d.get('demise_identified') is not False for d in demises)
        and all(number(r['annual_rent']) for r in rows)
        and len({r['unit'].strip().casefold() for r in rows}) == len(rows)
        and rounded(sum(r['annual_rent'] for r in rows)) == rounded(total))
    if reconciled:
        for row in rows:
            row['share_pct'] = rounded(row['annual_rent']/total*100) if total else None
        explanation = 'These rents total £' + f'{total:,.2f}'.removesuffix('.00') + ' a year.'
        if any(d.get('residential_reversion') for d in demises):
            explanation += ' The flats contribute ground rent only; the buyer does not receive their residential letting income.'
    elif rows:
        explanation = ('These are amounts recorded in the lease documents, not a confirmed current income schedule. '
                       'Earlier leases or later changes may cover the same unit, so the amounts have not been added together.')
    else:
        explanation = 'The supplied documents do not yet identify the individual sources of rental income.'
    return {'rows': rows, 'reconciled': reconciled, 'total': total if reconciled else None,
            'explanation': explanation}


def energy_schedule(report):
    if not _pack(report):
        return []
    try:
        as_of = date.fromisoformat(str(report.get('created_at', ''))[:10])
    except ValueError:
        as_of = None
    rows = []
    for d in report.get('investigation', {}).get('demises', []):
        if not d.get('document') or d.get('residential_reversion') or d.get('demise_identified') is False:
            continue
        cert = d.get('epc') or {}
        source = cert.get('source')
        # A rating without its source is not a customer-verifiable certificate.
        matched = bool(source and cert.get('rating'))
        if matched:
            position = 'EPC rating ' + str(cert['rating'])
            try:
                expiry = date.fromisoformat(str(cert.get('valid_until', '')))
            except ValueError:
                expiry = None
            if expiry:
                position += ('; expired ' if as_of and expiry < as_of else '; valid until ') + expiry.strftime('%d %B %Y').lstrip('0')
            else:
                position += '; expiry date not established'
            detail = ('Certificate address: ' + cert['address'] + '. ') if cert.get('address') else ''
            detail += cert.get('scope_note') or 'The certificate is associated with this unit; its assessed floors and extent still need checking against the lease plan.'
        else:
            position = 'No matching EPC identified'
            detail = 'Confirm whether a certificate or exemption applies before allowing for energy-improvement costs or relying on future letting.'
        rows.append({'unit': d.get('label') or 'Unit not identified', 'position': position,
                     'detail': detail, 'matched': matched,
                     'evidence': [source] if matched else d.get('evidence', [])})
    return rows


def schedule_blocks(report, section, references):
    """The same computed tables survive both template and written narratives."""
    blocks = []
    if section == 'income':
        schedule = income_schedule(report)
        if not schedule['rows']:
            return blocks
        def money(v):
            return 'Not established' if v is None else '£' + f'{v:,.2f}'.removesuffix('.00')
        rows = [[r['unit'], r['income_type'], money(r['annual_rent']),
                 f"{r['share_pct']:.1f}%" if r['share_pct'] is not None else '—'] for r in schedule['rows']]
        if schedule['reconciled']:
            rows.append(['Total annual rent', '', money(schedule['total']), '100%' if schedule['total'] else '—'])
        blocks.append({'kind': 'table', 'headers': ['Unit', 'Income', 'Annual rent', 'Share'],
                       'rows': rows, 'widths': [.36, .30, .21, .13]})
        blocks.append({'kind': 'p', 'style': 'small', 'text': schedule['explanation']})
        evidence = [e for r in schedule['rows'] for e in r['evidence']]
        context = 'Property units and rental income'
    elif section == 'property':
        rows = energy_schedule(report)
        if not rows:
            return blocks
        blocks.append({'kind': 'h', 'text': 'Energy Performance Certificates (EPCs)'})
        blocks.append({'kind': 'table', 'headers': ['Unit', 'Certificate position'],
                       'rows': [[r['unit'], r['position']] for r in rows], 'widths': [.43, .57]})
        for row in rows:
            blocks.append({'kind': 'p', 'style': 'small', 'text': row['unit'] + ': ' + row['detail']})
            refs = references.add(row['evidence'], 'EPC: ' + row['unit'])
            if refs:
                blocks.append({'kind': 'evidence', 'rows': refs})
        low_rated = [r['unit'] for r in rows if r['matched'] and r['position'].startswith(('EPC rating F', 'EPC rating G'))]
        if low_rated:
            blocks.append({'kind': 'p', 'style': 'small',
                'text': 'The low rating for ' + ', '.join(low_rated) + ' needs assessment against the applicable letting requirements and any valid exemption. Required improvements could affect the purchase budget and the time needed to relet.'})
        evidence = []
        context = 'Energy Performance Certificates'
    else:
        return blocks
    refs = references.add(evidence, context)
    if refs:
        blocks.append({'kind': 'evidence', 'rows': refs})
    for block in blocks:
        block['role'] = section + '_schedule'
    return blocks
