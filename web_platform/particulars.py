"""Source-preserving particulars: group facts, remove repetition, never invent prose."""
import re
from collections import OrderedDict
from html import unescape

TITLES = ('Description', 'Key Investment Points', 'Accommodation', 'Tenancy', 'Lease',
          'Tenure', 'Planning / Development Potential', 'VAT', 'EPC', 'Location',
          'Other Important Information')
HEADINGS = {'particulars': 'Description', 'property': 'Description', 'description': 'Description',
    'summary': 'Key Investment Points', 'property summary': 'Key Investment Points',
    'key features': 'Key Investment Points', 'accommodation': 'Accommodation',
    'tenancy schedule': 'Tenancy', 'tenancy': 'Tenancy', 'tenancies': 'Tenancy',
    'lease': 'Lease', 'tenure': 'Tenure', 'planning': 'Planning / Development Potential',
    'vat': 'VAT', 'epc': 'EPC', 'epc rating': 'EPC', 'energy performance certificate': 'EPC',
    'location': 'Location', 'situation': 'Location', 'additional information': 'Other Important Information',
    'services': 'Other Important Information', 'local authority': 'Other Important Information'}


def clean(value):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))).strip()


def key(value):
    return re.sub(r'[^a-z0-9£%]+', '', value.lower())


def structured_particulars(row):
    sections = OrderedDict((t, []) for t in TITLES)
    seen = set()
    def add(section, text):
        text = clean(text).strip(' .•*:-')
        signature = key(text)
        if len(signature) < 3 or signature in seen:
            return
        seen.add(signature)
        sections[section].append(text)

    text = unescape(re.sub(r'<(?:br\s*/?|/p|/li|/div)>', '\n', row.get('description') or '', flags=re.I))
    text = re.sub(r'<[^>]+>', ' ', text)
    if row.get('tenancy_schedule'):
        text = re.split(r'Tenancy schedule:', text, maxsplit=1, flags=re.I)[0]
    # Recover explicit source headings, including legacy collectors which flattened HTML.
    labels = '|'.join(sorted((re.escape(x) for x in HEADINGS), key=len, reverse=True))
    heading = re.compile(r'(?i)(?<!\w)(' + labels + r')\s*:\s*')
    text = heading.sub(lambda m: '\n@@' + HEADINGS[m.group(1).lower()] + '@@\n', text)
    uppercase = re.compile(r'(?<!\w)(PROPERTY|SITUATION|SERVICES|LOCAL AUTHORITY|ENERGY PERFORMANCE CERTIFICATE)(?!\w)')
    text = uppercase.sub(lambda m: '\n@@'+HEADINGS[m.group(1).lower()]+'@@\n', text)
    current = None
    for part in re.split(r'(@@[^@]+@@)', text):
        if part.startswith('@@'):
            current = part.strip('@')
            continue
        part = re.split(r'Viewings\s+Contact Auction Estates|Important notices|Conditions of Sale',part,maxsplit=1,flags=re.I)[0]
        # Keep numeric dates, decimal values, abbreviations and lease clauses intact.
        for sentence in re.split(r'\n+|[•¢]\s*|(?<=[.!?])\s+(?=[A-Z])', part):
            sentence = clean(sentence)
            if not sentence:
                continue
            if re.match(r'^(?:Register to bid|Share this|Download brochure|Cookie|Accept all)\b', sentence, re.I):
                continue
            destination = current if current not in ('Description','Key Investment Points') else None
            if current=='Tenure' and re.search(r'\b(?:let on|let to|tenant)\b',sentence,re.I):
                destination=None
            if not destination:
                for pattern, section in (
                    (r'\b(?:VAT|option to tax|TOGC)\b', 'VAT'),
                    (r'\b(?:EPC|energy performance)\b', 'EPC'),
                    (r'\b(?:planning|STPP|development potential|conversion)\b', 'Planning / Development Potential'),
                    (r'\b(?:lease|break option|break clause|rent review|FRI|IRI)\b', 'Lease'),
                    (r'\b(?:rent|rental|let to|tenan|vacant|occupation)\w*\b', 'Tenancy'),
                    (r'\b(?:freehold|leasehold)\b', 'Tenure'),
                    (r'\b(?:sq\.?\s*(?:ft|m)|acres|accommodation|floor area|ground floor|first floor|sales area|stock room|frontage|kitchen)\b', 'Accommodation'),
                    (r'\b(?:nearby|situated|located|location|fronting)\b', 'Location'),
                    (r'\b(?:rates|service charge|ground rent|arrears|covenant|parking)\b', 'Other Important Information')):
                    if re.search(pattern, sentence, re.I):
                        destination = section
                        break
            add(destination or current or 'Description', sentence)

    source_text = key(clean(row.get('description')))
    lease_in_source = bool(sections['Lease'])
    # Structured fields fill gaps. Never repeat a value already present in source prose.
    def fact(section, label, field, unit=''):
        value = row.get(field)
        if value is None or value == '' or isinstance(value, (bool, list, dict)):
            return
        rendered = f'{value:,.0f}' if isinstance(value, (int, float)) else clean(value)
        if key(rendered) in source_text or rendered.lower() in ('unknown', 'not stated', 'mentioned - verify'):
            return
        # A complete source lease/tenant sentence is preferable to a truncated parser fragment.
        if section=='Lease' and lease_in_source:
            return
        if field=='tenant' and re.search(r'\b(?:let to|tenant|lease.{0,20}to)\b',clean(row.get('description')),re.I):
            return
        add(section, label + ': ' + rendered + unit)

    for section, label, field, unit in (
        ('Accommodation','Floor area','area_sqft',' sq ft'),
        ('Accommodation','Site area','site_area_acres',' acres'),
        ('Tenancy','Tenant','tenant',''), ('Tenancy','Occupation','occupation',''),
        ('Lease','Lease term','lease_term',''), ('Lease','Lease start','lease_start',''),
        ('Lease','Lease expiry','lease_expiry',''), ('Lease','Break','break_clause',''),
        ('Lease','Rent review','rent_review',''), ('Tenure','Tenure','tenure',''),
        ('VAT','Source VAT status','vat_status',''), ('EPC','EPC','epc',''),
        ('Other Important Information','Parking','parking',''),
        ('Other Important Information','Listed status','listed_status','')):
        fact(section,label,field,unit)
    for label,field in (('Rateable value','rateable_value'),('Ground rent p.a.','ground_rent'),('Service charge','service_charge'),('Arrears reported','arrears')):
        value=row.get(field)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and key(f'{value:,.0f}') not in source_text:
            add('Other Important Information',f'{label}: £{value:,.0f}')
    if row.get('historic_rent') is not None:
        add('Tenancy', f'Previous / historic rent: £{row["historic_rent"]:,.0f} per annum — not current income')
    if row.get('erv') is not None:
        add('Tenancy', f'Estimated rental value: £{row["erv"]:,.0f} per annum — not current income')
    return [{'title':title, 'items':items} for title,items in sections.items() if items]
