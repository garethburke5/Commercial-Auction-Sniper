"""Cross-evidence investment investigation with explicit scope and uncertainty.

No property names or specimen narratives belong here. The systematic layer
connects reusable facts and exposes unanswered research. Open-ended review is a
separate, provenance-bound stage; missing review cannot become a paid approval.
"""
from __future__ import annotations
from datetime import date, datetime
from hashlib import sha256
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite
import re

from acquisition_evidence_graph import (norm, build_ledger, validate_external_research,
                                        reasoning_packet, validate_open_review)


def cash(value):
    if not isinstance(value, (int, float, Decimal)) or isinstance(value, bool) or not isfinite(value):
        return 'Not established'
    return '£' + format(value, ',.0f' if value == int(value) else ',.2f')


def ratio(numerator, denominator):
    if not isinstance(numerator, (int, float)) or not denominator:
        return None
    return float((Decimal(str(numerator)) / Decimal(str(denominator)) * 100).quantize(
        Decimal('.01'), rounding=ROUND_HALF_UP))


def _label(document):
    document = document.rsplit('::', 1)[-1].rsplit('/', 1)[-1]
    name = re.sub(r'(?:\.(?:pdf|docx?))+$', '', document, flags=re.I)
    name = re.sub(r'^Official Copy\s*\(Lease\)\s*[\d.]+\s*-\s*[A-Z]{1,3}\d+\s*-\s*', '', name, flags=re.I)
    name = re.sub(r'^Lease\s*(?:\([^)]*\))?\s*-?\s*', '', name, flags=re.I)
    return re.sub(r'\s+\d{2}[-./]\d{2}[-./]\d{4}\s*$', '', name).strip() or document


def _date(value):
    value = norm(value).replace('[', '').replace(']', '').strip()
    for fmt in ('%Y-%m-%d', '%d %B %Y', '%d %b %Y', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _source(record):
    if record.get('pack_evidence'):
        return record['pack_evidence']
    source = record.get('source', {})
    return {'document': source.get('title') or source.get('id'), 'url': source.get('url'),
            'excerpt': record.get('quote'), 'observed_at': source.get('observed_at'),
            'source_kind': 'external'}


def _scope_matches(record, demise):
    # An explicit source-checked document association is preferable to fuzzy
    # address matching. A postcode alone never links a certificate to a demise.
    if record.get('demise_document'):
        return record['demise_document'] == demise.get('document')
    def address(value):
        value = norm(value).casefold().replace('–', '-').replace('—', '-')
        value = re.sub(r'\bst\.?\b', 'street', value)
        value = re.sub(r'\brd\.?\b', 'road', value)
        return norm(re.sub(r'[^a-z0-9 /-]', ' ', value))
    label = address(demise.get('label', ''))
    # Match the full unit/address, optionally followed by comma-separated
    # locality. Substring matching joins 1 to 11 and a shop to an upper flat.
    subject = address(record.get('subject', ''))
    street = address(str(record.get('subject') or '').split(',')[0])
    return bool(label and len(label) > 5 and label in (subject, street))


def _profile(report, model, catalogue):
    text = norm(catalogue.get('description', ''))
    leases = model.get('lease_details', [])
    residential = [x for x in leases if x.get('interest') == 'Residential long lease']
    tenure = norm(report.get('tenure'))
    occupation = norm(catalogue.get('occupation') or catalogue.get('vacancy'))
    docs = ' '.join(d.get('document', '') for d in model.get('documents', []))
    from property_summary import specialist_use
    return {'use': specialist_use(catalogue) or catalogue.get('property_type') or 'Use not established',
            'jurisdiction': catalogue.get('country') or catalogue.get('jurisdiction') or 'Not established',
            'tenure': tenure or 'Not established',
            'vacant': bool(re.search(r'^vacant', occupation, re.I)),
            'leasehold_interest': bool(re.search(r'leasehold', tenure, re.I)),
            'listed': bool(re.search(r'\b(?:Grade\s+(?:I{1,3}|[123])\*?\s+Listed|listed building)\b', text, re.I)),
            'long_lease_reversions': bool(residential),
            # Several lease documents may be successive interests in one unit.
            # Only a reconciled schedule may establish multiple current lets.
            'multi_let': None if len(leases) > 1 else False,
            'development': bool(re.search(r'(?:property|site|unit) (?:is |has |offers |comprises )?(?:a |an )?(?:development opportunity|conversion opportunity|shell)|shell (?:and|&) core|shell condition|development site', text, re.I)),
            'new_build': bool(re.search(r'NHBC|building control.*commercial|warranty', docs, re.I)),
            'high_rise_evidence': bool(re.search(r'high-rise|building safety|EWS1|cladding', docs, re.I)),
            'source': 'Catalogue context and identified pack document roles; verify extent'}


def investigate(report, model, catalogue=None, research=None, open_review=None):
    catalogue = catalogue or {}
    research = validate_external_research(research or catalogue.get('research'))
    result_prices = [r for r in research['records'] if r['kind']=='subject_sale_result' and norm(r.get('subject')).casefold()==norm(report['property']).casefold() and isinstance(r.get('price'),(int,float))]
    report['assessment_price'] = result_prices[-1]['price'] if result_prices else report.get('guide_upper') or report.get('guide')
    report['assessment_price_basis'] = 'Auctioneer-reported sale price' if result_prices else 'Upper guide' if report.get('guide_upper') else 'Guide price'
    ledger = build_ledger(model, catalogue, research)
    profile = _profile(report, model, catalogue)
    designations=[r for r in research['records'] if r.get('kind')=='heritage_designation'
                  and norm(r.get('subject')).casefold()==norm(report['property']).casefold()
                  and re.search(r'Grade:\s*(?:II\*?|I)\b',r.get('quote',''))]
    if designations:profile['listed']=True
    findings, questions, demises = [], [], []
    as_of = _date(str(report.get('created_at', ''))[:10]) or date.today()

    def add(key, title, finding, consequence, resolution, evidence=(),
            state='unresolved', materiality='price_sensitive', topic='investment',
            exposed_rent=None, reasoning=None, summary=None):
        item = {'id': key, 'title': title, 'finding': finding, 'state': state,
                'materiality': materiality, 'topic': topic, 'consequence': consequence,
                'resolution': resolution, 'evidence_ids': ledger.add_many(evidence),
                'evidence': list(evidence), 'exposed_annual_rent': exposed_rent,
                'reasoning': reasoning or consequence, 'summary': summary or finding}
        findings.append(item)
        return item

    def question(key, text, why, topics, decision=True):
        attempts = [a for a in research['attempts'] if a.get('topic') in topics
                    and a.get('status') not in ('not_attempted', 'not_captured', 'capture_limited')
                    and (not a.get('question_id') or a['question_id'] == key)]
        questions.append({'id': key, 'question': text, 'why': why,
                          'topics':topics,
                          'decision_relevant': decision,
                          'status': 'investigated_with_limits' if attempts else 'not_investigated',
                          'attempts': attempts})

    catalogue_evidence = [r for r in ledger.records.values() if r.get('source_kind') == 'catalogue']
    for amendment in report.get('amendment_review', []):
        add('addendum-' + sha256(str(amendment).encode()).hexdigest()[:10],
            'Later auction addendum changes the acquisition-cost basis',
            'A source-captured amendment has been checked against the transaction. Status: ' + amendment['status'].replace('_',' ') + '.',
            'Earlier conditions must not be used to understate completion cash or to charge the same seller contribution twice.',
            amendment.get('remaining_question') or 'Resolve the scope and effect of this addendum before relying on the acquisition budget.',
            [amendment['evidence']], state='confirmed', materiality='routine' if amendment['status']=='applied_limited_cost_amendment' else 'decision_gate', topic='costs')

    # Leases remain separate until their demises and temporal relationship are
    # established. Do not silently choose a later lease or sum conflicting ones.
    for lease_index, lease in enumerate(model.get('lease_details', []), 1):
        label = lease.get('demise') or _label(lease['document'])
        identified = bool(lease.get('demise') or re.search(r'\b(?:(?:unit|shop)\s+\w|flat\b|arcade\b|\d+\s+[A-Za-z]+\s+(?:Street|Road|Square|Lane|Avenue))', label, re.I))
        if not identified:
            label = f'Lease document {lease_index} — unit unresolved'
        row = {'id': sha256(lease['document'].encode()).hexdigest()[:12],
               'document': lease['document'], 'label': label, 'demise_identified': identified,
               'tenant': lease.get('tenant'), 'annual_rent': lease.get('annual_rent'),
               'rent_deposit': lease.get('rent_deposit'), 'guarantee': lease.get('guarantee'),
               'interest': lease.get('interest'), 'term': lease.get('term'),
               'lease_date': lease.get('lease_date'), 'lease_date_evidence': lease.get('lease_date_evidence',[]),
               'breaks': lease.get('breaks', []), 'reviews': lease.get('reviews', []),
               'security': lease.get('security'),
               'evidence': lease.get('evidence', []), 'epc': None,
               'residential_reversion': lease.get('interest') == 'Residential long lease'}
        demises.append(row)
        if lease.get('security'):
            security = lease['security']
            add('renewal-rights-' + row['id'], 'The lease intends to exclude automatic renewal rights',
                security['position'],
                'If the exclusion procedure was valid, the tenant has no automatic right to renew under the Landlord and Tenant Act 1954. This affects possession and reletting at expiry; it does not guarantee future rent.',
                security['action'], security.get('evidence', []), topic='lease')
    if not demises:
        demises.append({'id': 'subject', 'label': report.get('property'), 'document': None,
                       'tenant': report.get('tenant'), 'annual_rent': report.get('rent'),
                       'interest': 'Vacant sale' if profile['vacant'] else 'Interest requires verification',
                       'breaks': [], 'reviews': [], 'evidence': [], 'residential_reversion': False})

    from acquisition_financials import number
    rents = [x['annual_rent'] for x in demises]
    comparable_income = (not profile['vacant'] and len(rents) > 0 and
                         all(d.get('document') and d.get('evidence') and d.get('demise_identified') for d in demises) and
                         all(number(r) for r in rents) and
                         number(report.get('rent')) and
                         abs(sum(rents) - report['rent']) < .01)
    same_demise = len({d['label'].lower() for d in demises}) < len(demises)
    temporal_conflict = any(d.get('temporal_status') in ('STATED TERM ENDED / HOLDING OVER UNCONFIRMED','DRAFT / UNCERTAIN','FUTURE STATED TERM') for d in report.get('lease_reconciliation', []))
    income_reconciled = comparable_income and not same_demise and not temporal_conflict
    if income_reconciled:profile['multi_let']=len(demises)>1

    # A repair clause is not a net-income warranty. Carry the actual allocation
    # into the investment assessment, including long-lease reversion duties.
    repair_leases = [l for l in model.get('lease_details', []) if l.get('repairs')]
    if repair_leases:
        repair_evidence = [e for l in repair_leases for r in l['repairs']
                           for e in r.get('evidence', [])]
        add('repair-recovery', 'Landlord obligations and tenant recovery must be reconciled',
            ' '.join(_label(l['document']) + ': ' + ' '.join(r['text'] for r in l['repairs'])
                     for l in repair_leases),
            'The party obliged to organise or fund work is not necessarily the party that ultimately pays. '
            'Lease recovery rights do not prove full recovery or timely payment; voids and disputes can leave a landlord cash shortfall.',
            'Map each roof, structure, shared service and insurance obligation to the relevant demise, '
            'lease clause and recoverable share. Obtain the current budget, reserve balance, arrears and planned works.',
            repair_evidence, state='unresolved', materiality='price_sensitive', topic='repairs')
    if income_reconciled:
        add('income-reconciliation', 'Lease rents reconcile to the advertised total',
            f"{len(rents)} separately identified lease rents total {cash(sum(rents))} a year.",
            'This supports the contractual income total. It does not establish collection, arrears or tenant solvency.',
            'Reconcile a current tenant ledger and all later concessions or variations.',
            [e for d in demises for e in d['evidence']], state='confirmed', materiality='information', topic='income')
    elif not profile['vacant']:
        add('income-unreconciled', 'Current contractual income is not fully reconciled',
            ('The supplied lease amounts cannot safely be aggregated into the advertised current income.'
             if model.get('lease_details') else 'Operative leases were not supplied; the advertised rent remains a published claim.'),
            'A yield based on an unreconciled rent can overstate the income being acquired; earlier leases, variations and concessions must be resolved.',
            'Produce a demise-by-demise schedule of the operative lease, current reserved rent and payment evidence.',
            [e for d in demises for e in d['evidence']], state='unresolved', materiality='decision_gate', topic='income')

    commercial = [x for x in demises if not x['residential_reversion']]
    from acquisition_energy import pack_certificates
    certificates_in_pack = pack_certificates(model,demises)
    unresolved_demises = [d for d in commercial if d.get('document') and not d.get('demise_identified')]
    if unresolved_demises:
        add('lease-extent-unresolved', 'Lease documents are not a verified tenancy schedule',
            'The physical extent and current status of '+str(len(unresolved_demises))+' lease document(s) remain unresolved. They have not been counted as separate current lettings.',
            'Earlier leases, renewals and retained interests can refer to the same accommodation. Adding them or assigning an EPC to each would misstate the investment.',
            'Reconcile the operative leases, variations, assignments and plans to the current sale extent and tenant schedule.',
            [e for d in unresolved_demises for e in d['evidence']], materiality='decision_gate', topic='ownership')
    for row in commercial:
        if row in unresolved_demises:
            continue
        certificates = [r for r in research['records'] + certificates_in_pack if r['kind'] == 'epc_certificate' and _scope_matches(r, row)]
        pack_epcs = [f for f in model.get('findings', []) if f.get('title') == 'Energy rating in the certificate']
        if len(commercial) == 1 and len(pack_epcs) == 1:
            # A sole certificate is a candidate, not silently a verified match.
            row['pack_epc_candidate'] = pack_epcs[0]
        if certificates:
            cert = sorted(certificates, key=lambda r: r.get('lodged_on') or '', reverse=True)[0]
            row['epc'] = {k: cert.get(k) for k in ('rating', 'score', 'address', 'floor_area_sqm', 'valid_until', 'certificate_number', 'lodged_on')}
            row['epc']['source'] = _source(cert)
            row['epc']['scope_note'] = cert.get('scope_note') or 'Address association checked; confirm the assessed physical extent against the demise plan.'
            expiry = _date(cert.get('valid_until', ''))
            if expiry and expiry < as_of:
                add('epc-expired-' + row['id'], 'Expired energy certificate: ' + row['label'],
                    f"The matched {cert.get('rating')} certificate expired on {cert.get('valid_until')}.",
                    'The historic rating does not establish current sale/letting compliance or the cost of reletting.',
                    'Check when a valid EPC was supplied for this sale, any continuing marketing, and any new letting or works trigger. Expiry alone during an unchanged tenancy does not establish a renewal duty or a MEES breach.',
                    [_source(cert)], state='confirmed', materiality='routine', topic='energy', exposed_rent=row.get('annual_rent'))
            if cert.get('rating') in ('F', 'G'):
                add('epc-substandard-' + row['id'], 'Substandard rating needs a letting-compliance assessment',
                    f"The matched certificate rates {row['label']} {cert['rating']}.",
                    'If the relevant tenancy is within MEES, continued letting needs improvement or a valid exemption; works, downtime and finance conditions can affect value.',
                    'Check tenancy scope, the applicable jurisdiction, registered exemption evidence and a costed improvement plan.',
                    [_source(cert)] + row['evidence'], state='unresolved', materiality='decision_gate', topic='energy', exposed_rent=row.get('annual_rent'))
        else:
            candidate = row.get('pack_epc_candidate')
            finding = ('An EPC is supplied but its address/demise, validity and applicable letting scope have not been reconciled.' if candidate else
                       'No current certificate has been matched to this commercial demise in the supplied and researched evidence.')
            if row.get('lease_date'):
                finding = 'The commercial lease is dated '+row['lease_date']+'. '+finding
            listing_note = (' Listed status is not an automatic exemption. The historic-building exception depends on unacceptable alteration of character or appearance; establish the actual improvement options and consent position.' if profile['listed'] else '')
            rent_note = (f" The identified lease rent is {cash(row['annual_rent'])} a year" +
                        (f" ({ratio(row['annual_rent'], report['rent']):.1f}% of the advertised income)." if income_reconciled else '.')) if row.get('annual_rent') else ''
            if not row.get('document'):
                finding='The sale/letting extent and certificate coverage have not been reconciled to operative documents.'
                rent_note=(' The published whole-property rent is '+cash(report.get('rent'))+' a year; no lease-verified unit allocation is available.') if report.get('rent') else ''
            primary_guidance = [r for r in research['records'] if r['kind'] == 'regulatory_guidance' and profile['jurisdiction'] in r.get('jurisdictions', [])]
            negative_checks = [r for r in research['records'] if r['kind'] in ('epc_search','exemption_search') and _scope_matches(r,row)]
            findings_from_search = ' '.join(r.get('result_summary','') for r in negative_checks)
            applicability = (' England/Wales rules apply to qualifying new commercial lettings from April 2018 and continuing lettings from April 2023. The certificate requirement still depends on building/part, fixed conditioning services and any evidenced non-requirement.' if primary_guidance and profile['jurisdiction'] in ('England','Wales') else ' Applicable local regulation has not been established from researched primary guidance.')
            if re.search(r'\b(?:FIVE|5) years\b', str(row.get('term')), re.I) and primary_guidance:
                applicability += ' The stated five-year term does not appear to fall within the short-term or 99-year tenancy exclusions.'
            add('epc-scope-' + row['id'], 'Energy compliance unresolved: ' + row['label'],
                finding + listing_note + (' ' + findings_from_search if findings_from_search else '') + applicability,
                'The letting date, certificate requirement and MEES scope must be assessed together. Potential consequences include improvement expenditure, enforcement, restricted reletting and lender/resale objections; no breach or works cost is established.' + rent_note,
                'Match the exact unit and assessment extent on the official EPC register; obtain the certificate or documented non-requirement, and check any PRS exemption, its evidence, expiry and purchaser position.',
                row['evidence'] + row.get('lease_date_evidence',[]) + ([e for e in candidate.get('evidence', [])] if candidate else []) + [_source(r) for r in primary_guidance+negative_checks],
                state='unresolved' if candidate else 'missing', materiality='decision_gate', topic='energy', exposed_rent=row.get('annual_rent'),
                summary=finding+(' Listed status does not automatically remove EPC or MEES obligations; establish the lawful basis and practicable improvements.' if profile['listed'] else '')+
                    (' The recorded register searches were inconclusive for this demise; they do not prove non-compliance.' if negative_checks else '')+
                    (' The letting must be assessed against the applicable EPC and MEES rules in force at its date.' if primary_guidance else 'Applicable regulation still requires primary-source verification.'))
    question('energy-research', 'Resolve EPC and exemption evidence for each commercial demise.',
             'A certificate for another unit does not demonstrate compliance of the income-producing accommodation.', ['epc', 'exemptions'])

    if income_reconciled and commercial:
        largest = max(commercial, key=lambda d: d.get('annual_rent') or 0)
        concentration = ratio(largest['annual_rent'], report['rent'])
        if concentration and concentration >= 50:
            break_text = '; '.join(x.get('date_raw', '') for x in largest['breaks'])
            add('income-concentration', 'Income depends on one principal letting',
                f"{largest['label']} supplies {cash(largest['annual_rent'])} a year, {concentration:.1f}% of total rent." +
                (f' Tenant break wording: {break_text}.' if break_text else ''),
                f"A full year without that rent leaves {cash(report['rent']-largest['annual_rent'])} before landlord costs. A multi-unit building can still have concentrated income risk.",
                'Test affordability and covenant evidence, break notices and the cost/time required to relet the principal unit.',
                largest['evidence'] + [e for b in largest['breaks'] for e in b.get('evidence', [])],
                state='inference', materiality='price_sensitive', topic='income', exposed_rent=largest['annual_rent'])

    by_topic = {}
    for f in report.get('findings', []):
        by_topic.setdefault(f.get('section'), []).append(f)
    property_findings = model.get('transaction_findings', [])
    exclusions = [f for f in property_findings if 'excluded' in f.get('title', '').lower()]
    hazards = [f for f in property_findings if re.search(r'groundwater|flood|ground instability|subsidence', f.get('title', ''), re.I)]
    if exclusions:
        add('cover-hazard-interaction', 'Insurance exclusions must be tested against the building risks',
            ' '.join(f['found'] for f in exclusions),
            ('The pack also identifies modelled ground/flood hazards. The combination can leave a material loss uninsured and affect lender acceptance; a model is not proof of damage.' if hazards else
             'An excluded event can leave the purchaser exposed to rebuilding, rent loss and lender conditions. Existing tenant cover is not a purchaser insurance quotation.'),
            'Obtain a binding purchaser policy, survey/claims evidence and written lender acceptance; compare the cover with every relevant lease obligation.',
            [e for f in exclusions + hazards for e in f.get('evidence', [])],
            state='inference', materiality='decision_gate', topic='insurance')

    # Preserve the specificity already recovered by specialist extractors, while
    # ranking according to investment consequence rather than alphabetical IDs.
    for f in property_findings:
        title, fid = f.get('title', ''), f.get('id', '')
        if f in exclusions or f in hazards:
            continue
        materiality = 'price_sensitive'
        if re.search(r'negative|no current rent arrears|contaminated-land screening conclusion|Ground rent has a future', title, re.I):
            materiality = 'information'
        if re.search(r'Commercial EPC promised|asbestos enquiry reply', title, re.I):
            materiality = 'routine'
        if re.search(r'Tenant break|Edited lease dates', title):
            materiality = 'price_sensitive'
        add(fid, title, f.get('found', ''), f.get('meaning') or f.get('why'),
            f.get('next_step'), f.get('evidence', []), state='unresolved',
            materiality=materiality, topic=f.get('section', 'building'))
    for f in report.get('findings', []):
        if f.get('id') in {x['id'] for x in findings+property_findings} or f.get('id', '').startswith('fact-'):
            continue
        if income_reconciled and f.get('title') == 'Separate leases record different rent amounts':
            continue
        if f.get('id') in {'seller-fee', 'disbursements-cap', 'works-balance', 'search-cost', 'enquiries'}:
            level = 'routine'
        elif f.get('id') == 'title-exclusion':
            # A boundary/vertical exclusion can be entirely ordinary. A loss
            # of income-producing space requires a plan-based finding.
            level = 'routine'
        elif f.get('id') in {'vat-conflict', 'seller-fee-conflict', 'fee-conflict'}:
            level = 'decision_gate'
        elif f.get('severity') == 'INFORMATION':
            continue
        else:
            level = 'price_sensitive'
        add(f['id'], f['title'], f.get('found', ''), f.get('meaning') or f.get('why'),
            f.get('next_step'), f.get('evidence', []), materiality=level, topic=f.get('section'))

    if profile['long_lease_reversions']:
        add('reversion-economics', 'Sold-off flats do not provide residential market rent or immediate redevelopment control',
            f"{len([d for d in demises if d['residential_reversion']])} residential long-lease interests are identified.",
            'Low ground rents can coexist with retained structure, insurance and management duties. The flats are not vacant-possession residential value available to this buyer.',
            'Reconcile repair/recovery shares, reserves, statutory notices and the precise freehold/leasehold boundaries.',
            [e for d in demises if d['residential_reversion'] for e in d['evidence']],
            state='inference', materiality='price_sensitive', topic='ownership')
    if profile['vacant']:
        add('vacancy-carry', 'No contracted income supports the acquisition today',
            'The catalogue describes vacant possession.',
            'Quoted ERV or a former tenant rent is not current income. Holding costs, incentives, fit-out and time to occupation reduce cash return before stabilisation.',
            'Obtain a lettability/condition review, service-charge and rates budget, competing supply and recent letting evidence.',
            catalogue_evidence, state='confirmed', materiality='decision_gate', topic='income')
    if profile['leasehold_interest']:
        add('superior-interest', 'The acquired lease controls value and ongoing liabilities',
            'The sale is described as a leasehold interest.',
            'Term, ground rent, permitted use, alienation, repair and service-charge provisions can constrain finance, resale and future occupation even with a long unexpired term.',
            'Reconcile the superior lease and sale demise, annual recurring charges, consent fees and any ground-rent review.',
            [e for d in demises for e in d['evidence']], materiality='decision_gate', topic='ownership')
    if profile['high_rise_evidence']:
        add('building-safety-scope', 'Commercial unit sits within a building-safety evidence set',
            'The pack contains high-rise/building-safety documentation.',
            'A commercial purchase requires analysis of the building-wide obligations and costs allocated by its lease. Residential leaseholder protections cannot simply be assumed to protect this interest.',
            'Check registration, the responsible parties, current safety/remediation information and the commercial cost-allocation clauses.',
            materiality='decision_gate', topic='building')
    if profile['new_build'] or profile['development']:
        add('development-deliverability', 'Development or new-build value depends on completion and deliverability',
            'New-build, warranty or development evidence is present.',
            'Permission or a warranty is not proof that conditions, obligations, fit-out and service connections are discharged or that occupation can begin at no further cost.',
            'Reconcile planning conditions/S106, building control, warranty exclusions, practical completion, utilities, fit-out scope and a costed delivery programme.',
            materiality='decision_gate', topic='development')

    market = assess_market(report, research['records'])
    question('market-rents', 'Test passing rent against comparable achieved lettings and current competing supply.',
             'An attractive gross yield can conceal over-renting and a lower reversionary income.', ['market_rent'])
    question('market-price', 'Find genuinely comparable achieved investment sales and vacant-possession evidence.',
             'Asking prices and auction guides alone cannot support an investment value or maximum bid.', ['market_sales', 'vacant_possession'])
    question('history', 'Find earlier asking prices and listing dates for the same property and ownership; compare the income and tenants then and now. Distinguish a listing-added date from evidence of the price on that date. Report ordinary asking-price differences concisely; investigate reasons only where evidence suggests a material change.',
             'History can reveal rent resets, recurring vacancy, failed sales or changes in use.', ['history'])
    if not profile['vacant']:
        question('covenant', 'Identify each commercial legal tenant separately from the trading name; investigate business history, latest full accounts, available unrestricted reserves/cash, liabilities, recent performance, rent receipts and deposit or guarantor. For charities use Charity Commission accounts and distinguish restricted funds from available reserves. A deficit alone does not establish financial weakness. Do not assume an individual tenant has company accounts.',
                 'A trading brand, receipt or Companies House active status is not evidence of financial strength.', ['covenant', 'payment'])
    question('planning', 'Check relevant designation, permissions and nearby development status for this address.',
             'Consent constraints and construction effects can alter expenditure, use and demand.', ['planning'])
    question('environment', 'Investigate location-specific flood, contamination and environmental evidence.',
             'Distinguish mapped screening from an observed defect and establish the exact site extent.', ['environment'])
    question('expenditure', 'Investigate condition, likely expenditure and who would bear the cost for this property.',
             'Use actual particulars, surveys, condition evidence and recovery terms; do not invent a works budget.', ['condition', 'capex'])
    question('accommodation', 'Establish the accommodation of each unit: floor-by-floor areas, measurement basis and the accommodation producing each rent. Distinguish EPC areas, quoted total areas, sales floors and storage.',
             'A total area or a rent per square foot is misleading if the compared space differs.', ['accommodation','market'])
    question('tax-and-rates', 'Check VAT against auction conditions and option-to-tax or transfer-of-going-concern evidence. Retrieve the exact unit rating assessment, effective date and current list year from the Valuation Office; check current empty-property multiplier, supplements, initial exemption and reliefs. Occupied charitable or small-business relief does not automatically apply to a vacant investment. Distinguish a constant-rate vacancy illustration from an actual bill across future tax years. Obtain current primary guidance for the jurisdiction.',
             'VAT cash requirements and holding costs can materially change acquisition expenditure and vacancy exposure.', ['tax','rates'])
    question('local-market', 'Assess local occupier demand, competing supply and rental sustainability for this property use.',
             'Market conditions must be relevant to the location, use and evidence date.', ['local_market'])

    scenario_rows = []
    price = report.get('assessment_price')
    if income_reconciled and price:
        scenario_rows.append({'label': 'Contract rent collected', 'rent': report['rent'], 'yield': ratio(report['rent'], price), 'assumption': 'Before costs and tax'})
        for d in commercial:
            if d['annual_rent']:
                scenario_rows.append({'label': 'Six-month void: ' + d['label'], 'rent': report['rent'] - d['annual_rent'] / 2,
                                      'yield': ratio(report['rent'] - d['annual_rent'] / 2, price),
                                      'assumption': 'Other rents unchanged; excludes rates, incentives, works and fees'})
        largest = max(commercial, key=lambda d:d.get('annual_rent') or 0) if commercial else None
        if largest and largest.get('annual_rent'):
            scenario_rows.append({'label':'Full-year void: '+largest['label'], 'rent':report['rent']-largest['annual_rent'], 'yield':ratio(report['rent']-largest['annual_rent'],price), 'assumption':'Illustrative principal-unit void, not a forecast; before holding costs'})
    physical_topics = {'fire', 'asbestos', 'insurance', 'service', 'title', 'conditions', 'epc', 'planning'}
    addressed_documents = {e.get('document') for f in findings for e in f['evidence']}
    addressed_documents.update(e.get('document') for f in model.get('findings', []) if f.get('fact') for e in f.get('evidence', []))
    substantive = [d['document'] for d in model.get('documents', []) if not re.search(r'^(?:ID requirements|terms and conditions for remote bidders|deposit terms|form of purchase agreement|auctioneer terms|common auction conditions)',d['document'],re.I)]
    unreviewed = [d for d in substantive if d not in addressed_documents]
    priority = {'decision_gate': 0, 'price_sensitive': 1, 'routine': 2, 'information': 3}
    findings.sort(key=lambda f: (priority[f['materiality']], -(f.get('exposed_annual_rent') or 0), f['id']))
    investigation = {'version': '1', 'profile': profile, 'demises': demises,
                     'income_reconciled': income_reconciled, 'findings': findings,
                     'market': market, 'scenarios': scenario_rows, 'research_questions': questions,
                     'external_research': research, 'evidence': list(ledger.records.values()),
                     'unreviewed_documents': unreviewed,
                     'open_review': {'completed': False, 'investment_approved': False,
                                     'limitations': ['Systematic relationships are not an open-ended investment review.']}}
    from acquisition_transcription import validate_visual_dispositions
    investigation.update(validate_visual_dispositions(model,catalogue.get('visual_dispositions',[])))
    if open_review:
        result = validate_open_review(open_review, reasoning_packet(report, investigation))
        investigation['open_review'] = result
        if result['provenance_valid']:
            disposed={}
            for item in result.get('document_dispositions',[]):
                if item['status']!='unresolved':
                    disposed.setdefault(item['document'],set()).update(item['source_ids'])
            # A useful review can clear a document without inventing an adverse
            # finding. Its disposition must account for every source from that
            # document, not just a selected page or familiar filename.
            for document,refs in disposed.items():
                expected={x['id'] for x in ledger.records.values() if x.get('document')==document}
                if expected and expected<=refs and document in investigation['unreviewed_documents']:
                    investigation['unreviewed_documents'].remove(document)
            for finding in result['findings']:
                if finding['id'] not in {f['id'] for f in findings}:
                    finding = dict(finding)
                    finding['origin'] = 'open_review'
                    finding['evidence'] = [ledger.records[x] for x in finding['evidence_ids']]
                    findings.append(finding)
            findings.sort(key=lambda f: (priority[f['materiality']], -(f.get('exposed_annual_rent') or 0), f['id']))
    return investigation


def assess_market(report, records):
    """Preserve evidence class; asking data cannot become an achieved valuation."""
    from acquisition_market_evidence import corpus_records
    records=list(records)+corpus_records(report.get('market_context'))
    market = [r for r in records if r['kind'] in {'rental_comparable', 'sale_comparable', 'marketing_history', 'subject_asking_sale', 'subject_asking_rent', 'planning_context', 'occupation_history'}]
    achieved_sales = [r for r in market if r['kind'] == 'sale_comparable' and r.get('price_basis') == 'achieved' and r.get('comparable') is True]
    achieved_rents = [r for r in market if r['kind'] == 'rental_comparable' and r.get('rent_basis') == 'achieved' and r.get('comparable') is True]
    asks = [r for r in market if r['kind'] == 'subject_asking_sale' and isinstance(r.get('price'), (int, float))]
    comments = []
    if asks and report.get('assessment_price'):
        ask = asks[0]['price']; price = report['assessment_price']
        if ask > 0:
            change = (price / ask - 1) * 100
            comments.append(f"The {cash(price)} assessment price is {abs(change):.1f}% {'below' if change < 0 else 'above'} the {cash(ask)} subject marketing ask. Basis: {report.get('assessment_price_basis', 'assessment input')}. This is price history, not evidence of a discount to market value.")
    comments.append('Achieved investment-sale evidence ' + ('has been recorded; differences still need valuation judgement.' if achieved_sales else 'has not been established at a sufficiently comparable level. The guide is not independently supported as fair value.'))
    comments.append('Achieved rental evidence ' + ('has been recorded; adjust for unit, size, condition, location, incentives and date.' if achieved_rents else 'has not been established. Asking rents provide context, not a proven ERV or reletting timescale.'))
    return {'records': market, 'comments': comments,
            'price_support': 'evidence_requires_adjustment' if achieved_sales else 'inconclusive',
            'erv_support': 'evidence_requires_adjustment' if achieved_rents else 'inconclusive',
            'valuation': None, 'maximum_bid': None}
