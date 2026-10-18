"""Transparent investor arithmetic, usable with no paid research provider.

Known costs, unknown costs and illustrative assumptions never share a total.
This is a sensitivity, not a valuation or a claim about market rent/expenses.
"""
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value >= 0


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def percent(income, capital):
    return rounded(income / capital * 100) if capital else None


def non_residential_sdlt(consideration):
    if not number(consideration):
        raise ValueError('A finite non-negative consideration is required')
    return rounded(min(max(consideration-150000,0),100000)*.02 + max(consideration-250000,0)*.05)


def financial_view(report):
    inv = report.get('investigation') or {}
    price = report.get('assessment_price')
    price = price if number(price) and price > 0 else None
    rent = report.get('rent')
    rent = rent if number(rent) else None
    costs = report.get('costs') or []
    valid_costs = [c for c in costs if number(c.get('amount'))]
    fixed = rounded(sum(c['amount'] for c in valid_costs)) if valid_costs else None
    subtotal = rounded(price + fixed) if price is not None and fixed is not None else None
    commercial = [d for d in inv.get('demises', []) if not d.get('residential_reversion')
                  and number(d.get('annual_rent')) and d.get('document') and d.get('evidence')]
    reconciled = bool(inv.get('income_reconciled') and commercial)
    principal = max(commercial, key=lambda d: d['annual_rent']) if reconciled else None
    scenarios = []
    # Use price alone if fees are unknown, and explicitly expose that denominator.
    denominator = subtotal or price
    if rent is not None and denominator:
        for label, haircut in [('Stated rent, before running costs', 0),
                               ('Illustrative 10% annual cost allowance', .1),
                               ('Illustrative 20% annual cost allowance', .2)]:
            allowance = rounded(rent * haircut)
            income = rounded(rent - allowance)
            scenarios.append({'label': label, 'rent_received': rent, 'cost_allowance': allowance,
                              'cash_before_finance_tax': income, 'return_pct': percent(income, denominator),
                              'assumption': 'Collection assumed; allowance is not a property-specific estimate.'})
        if principal:
            # Keep the annual cost allowance fixed during a void; do not assume
            # repair/management costs disappear with the lost rent.
            allowance = rounded(rent * .2)
            for months in (6, 12):
                received = rounded(rent - principal['annual_rent'] * months / 12)
                income = rounded(received - allowance)
                scenarios.append({'label': f'{months}-month main-unit void + 20% cost allowance',
                                  'rent_received': received, 'cost_allowance': allowance,
                                  'cash_before_finance_tax': income, 'return_pct': percent(income, denominator),
                                  'assumption': 'Other rents unchanged; allowance stays at 20% of full stated rent. '
                                  'Extra vacancy rates, works, incentives and reletting fees remain unquantified.'})
    price_rows = []
    if price and rent is not None:
        candidates = [price * .9, price, price * 1.1]
        for candidate in candidates:
            candidate = rounded(candidate)
            price_rows.append({'price': candidate, 'gross_yield': percent(rent, candidate),
                               'basis': 'Illustrative price sensitivity, not a market valuation or bid recommendation.'})
    profile=inv.get('profile') or {}
    tax=None
    if (price and profile.get('jurisdiction') in ('England','Northern Ireland')
            and str(profile.get('tenure','')).lower()=='freehold'
            and str(profile.get('use','')).lower() in ('mixed use','retail','office','industrial','commercial')):
        tax={'amount':non_residential_sdlt(price),
             'basis':'Illustrative non-residential/mixed-use SDLT on the price only. '
                     'Assumes a single freehold purchase, no reliefs and no additional chargeable consideration. '
                     'Confirm classification, linked transactions, VAT and seller-cost treatment.',
             'source':{'document':'HMRC: non-residential and mixed-use SDLT rates (checked 18 October 2026)',
                       'url':'https://www.gov.uk/stamp-duty-land-tax/nonresidential-and-mixed-rates'}}
    unknown_costs=['transaction tax and any VAT cash requirement', 'buyer legal and survey fees',
                   'finance costs', 'unrecoverable repairs and compliance work',
                   'void rates, insurance, incentives and reletting fees']
    if not any('auctioneer' in str(c.get('label','')).lower() for c in valid_costs):
        unknown_costs.insert(0,'auctioneer fee / buyer premium')
    if not any('seller' in str(c.get('label','')).lower() for c in valid_costs):
        unknown_costs.insert(0,'seller costs and reimbursements')
    return {'price': price, 'rent': rent, 'fixed_fees': fixed, 'known_subtotal': subtotal, 'illustrative_tax':tax,
            'denominator': denominator,
            'denominator_basis': 'price plus quantified fixed fees' if subtotal else 'price only; fees are not established',
            'principal': principal, 'income_reconciled': reconciled,
            'scenarios': scenarios, 'price_rows': price_rows,
            'unknown_costs': unknown_costs,
            'costs_complete': False}
