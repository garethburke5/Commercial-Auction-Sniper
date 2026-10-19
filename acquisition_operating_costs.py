"""Evidence-bound operating illustrations; never a claim of net profit.

Statement filenames do not establish periods. This deliberately narrow reader
accepts full calendar months whose credits/debits and management rows reconcile.
Unrecognised formats remain for the open evidence review, not guessed totals.
"""
from collections import defaultdict
from datetime import datetime
from calendar import monthrange
import hashlib
import re


def observed_management(sources, annual_rent):
    from acquisition_financials import number, rounded
    if not number(annual_rent) or not annual_rent:
        return None
    periods = defaultdict(dict)
    seen = set()
    conflicted = set()
    amount = r'(\d[\d,]*\.\d{2})'
    for source in sources:
        if source.get('source_kind') != 'legal_pack':
            continue
        text = source.get('text', '')
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        start = re.search(r'From Date:\s*(\d{2}/[A-Za-z]{3}/\d{2,4})', text)
        end = re.search(r'To Date:\s*(\d{2}/[A-Za-z]{3}/\d{2,4})', text)
        if not start or not end:
            continue
        try:
            dates = [datetime.strptime(x[1], '%d/%b/%Y' if len(x[1]) == 11 else '%d/%b/%y').date() for x in (start, end)]
        except ValueError:
            continue
        a, b = dates
        if a.day != 1 or (a.year, a.month) != (b.year, b.month) or b.day != monthrange(b.year, b.month)[1]:
            continue
        credits = re.findall(r'Total Credits:\s*' + amount, text)
        debits = re.findall(r'Total Debits:\s*' + amount, text)
        charges = re.findall(r'(?m)^.*?\bSupplier:\s*[^\n]*?\bManagement\s+' + amount + r'\s*$', text, re.I)
        units = re.findall(r'(?m)^.*?\d{2}/[A-Za-z]{3}/\d{2,4}\s+(?:=\s*)?\d+\s+(.+?)\s+Tenancy:', text)
        if len(credits) != 1 or len(debits) != 1 or len(charges) != 1 or len(units) != 1:
            continue
        credit, debit, charge = [float(x.replace(',', '')) for x in (credits[0], debits[0], charges[0])]
        if debit != charge or charge > credit:
            continue
        unit = re.sub(r'\W+', '', units[0]).casefold()
        key = a.isoformat()
        row = {'unit': unit, 'receipt': credit, 'management': charge, 'evidence': source}
        if unit in periods[key] and (periods[key][unit]['receipt'], periods[key][unit]['management']) != (credit, charge):
            conflicted.add(key)
        periods[key][unit] = row
    for period in sorted(periods, reverse=True):
        rows = list(periods[period].values())
        receipts = rounded(sum(r['receipt'] for r in rows))
        if period in conflicted or abs(receipts * 12 - annual_rent) > .12:
            continue
        monthly = rounded(sum(r['management'] for r in rows))
        annual = rounded(monthly * 12)
        return {'observed_month': period[:7], 'months_observed': 1,
                'monthly_receipts': receipts, 'monthly_management': monthly,
                'annualised_management': annual,
                'income_after_management_illustration': rounded(annual_rent - annual),
                'evidence': [r['evidence'] for r in rows],
                'basis': 'Illustration annualised from one month of reconciled management deductions. '
                         'Not verified annual expenses or operating profit. Excludes insurance, repairs, '
                         'vacancies, finance and tax; the buyer may have different management terms.'}
    return None


def return_headroom(income, capital, annual_costs=0, hurdles=(8, 10, 12)):
    from acquisition_financials import number, rounded
    if not all(number(x) for x in (income, capital, annual_costs)) or not capital:
        return []
    if not all(number(x) and x > 0 for x in hurdles):
        raise ValueError('Return thresholds must be finite positive percentages')
    return [{'hurdle_pct': h, 'required_annual_cash': rounded(capital*h/100),
             'annual_cost_capacity': rounded(income-annual_costs-capital*h/100),
             'annual_costs_already_deducted': rounded(annual_costs),
             'basis': 'Illustrative cash-return threshold before finance and tax. Capacity is the '
                      'allowance for OTHER costs after the stated deductions, not an expense estimate. '
                      'A negative capacity is a shortfall.'} for h in hurdles]


def empty_rates_scenarios(rateable_value, multiplier, *, supplement=0, exempt_months=3, months=(6, 12)):
    """A constant-rate sensitivity; caller must establish valuation and policy.

    No relief is inferred from a charitable tenant or occupied-property relief.
    A period crossing a tax year must be labelled as constant-rate, not a bill.
    """
    from acquisition_financials import number, rounded
    if not all(number(x) for x in (rateable_value, multiplier, supplement, exempt_months)):
        return []
    if multiplier > 1 or supplement > 1 or not all(number(x) for x in months):
        raise ValueError('Invalid rate multiplier or vacancy period')
    annual = rateable_value * (multiplier + supplement)
    return [{'months': m, 'chargeable_months': max(0, m-exempt_months),
             'empty_rates': rounded(annual*max(0, m-exempt_months)/12),
             'annual_charge_before_reliefs': rounded(annual),
             'basis': 'Constant-rate illustration after the stated initial exemption; not a council bill. '
                      'No charitable, occupied-property or transitional relief assumed.'} for m in months]
