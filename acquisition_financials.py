"""Transparent investor arithmetic, usable with no paid research provider.

Known costs, unknown costs and illustrative assumptions never share a total.
This is a sensitivity, not a valuation or a claim about market rent/expenses.
"""
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite
import re


def percentage_seller_cost(model, price):
    """Read a single explicit percentage contribution from special conditions.

    Percentage amounts are price-dependent; deposits and default charges are
    not additional seller fees. Conflicting clauses remain unresolved.
    """
    if not number(price):return {'cost':None,'conflict':False,'evidence':[]}
    names={d['document'] for d in model.get('documents',[]) if str(d.get('type','')).replace(' ','_')=='special_conditions'}
    candidates={};evidence=[]
    pattern=(r'(?:Buyer|Purchaser) shall pay to the Seller an amount equal to '
             r'(\d+(?:\.\d+)?)%\s*(plus (?:an amount equivalent to the current rate of value added tax|VAT))?'
             r'\s*of the Price as a contribution towards the (?:legal and agent[’\x27]s|legal|agent[’\x27]s) costs')
    for source in model.get('source_pages',[]):
        if source.get('document') not in names:continue
        text=re.sub(r'\s+',' ',source.get('text',''))
        for match in re.finditer(pattern,text,re.I):
            rate=float(match[1]);vat_rate=.2 if match[2] else 0
            if not 0<rate<100:continue
            candidates[(rate,vat_rate)]=True
            evidence.append({k:source[k] for k in ('document','document_sha256','page') if k in source}|{'excerpt':match.group()})
    if len(candidates)!=1:return {'cost':None,'conflict':len(candidates)>1,'evidence':evidence}
    rate,vat_rate=next(iter(candidates));base=rounded(price*rate/100);vat=rounded(base*vat_rate)
    return {'conflict':False,'evidence':evidence,'cost':{
        'label':'Seller legal and agent contribution','amount':rounded(base+vat),'base':base,'vat':vat,
        'percentage':rate,'price_basis':price,'evidence':evidence,
        'basis':f'{rate:g}% of the assessment price'+(' plus VAT modelled at 20%' if vat_rate else '; VAT not specified')}}


def historical_costs(report):
    """Recover a narrow service-charge total only when the printed sum reconciles.

    This is historic building spend, not a forecast or the landlord's net cost.
    Require the period, expenditure heading, component/subtotal arithmetic and
    one unambiguous total; never infer recovery percentages from this total.
    """
    rows = []
    for source in report.get('investigation', {}).get('evidence', []):
        text = source.get('text') or ''
        if source.get('source_kind') != 'legal_pack' or not re.search(r'(?:service.?charge|resi SC)\b', source.get('document', ''), re.I):
            continue
        period = re.search(r'Expendi?t?ure\s+(\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{4})', text, re.I)
        if not period or re.search(r'reserve|collected|% of total', text, re.I):
            continue
        amounts = [float(x.replace(',', '')) for x in re.findall(r'^\s*(\d[\d,]*(?:\.\d{1,2})?)\s*$', text, re.M)]
        # Recognise components -> subtotal -> other cost -> grand total.
        if len(amounts) < 5:
            continue
        total = amounts[-1]
        matches = [i for i in range(2, len(amounts)-2)
                   if rounded(sum(amounts[:i])) == amounts[i]
                   and rounded(amounts[i] + sum(amounts[i+1:-1])) == total]
        if len(matches) != 1:
            continue
        rows.append({'label': 'Historical service-charge expenditure', 'amount': total,
                     'period': period[1] + ' - ' + period[2],
                     'basis': 'Printed components reconcile to the total. Recovery, scope and recurrence remain unverified.',
                     'evidence': [source]})
    return rows


def investment_exposure(report, principal, rent, capital):
    """Decision-useful arithmetic without pretending unknown expenses are zero."""
    cases = []
    if principal and rent is not None:
        for months in (0, 6, 12):
            loss = rounded(principal['annual_rent'] * months / 12)
            cases.append({'label': 'Full stated rent' if not months else f'{months}-month principal-unit void',
                          'months': months, 'rent_lost': loss, 'rent_remaining': rounded(rent-loss),
                          'capital_return_pct': percent(rent-loss, capital),
                          'capital_basis': capital,
                          'basis': 'Other rents collected unchanged; before all holding, reletting, repair, finance and tax costs.'})
    from acquisition_operating_costs import return_headroom
    capacity = return_headroom(rent, capital)
    return cases, capacity


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


def unrecovered_cost_scenarios(rent, capital, amounts=(0, 5000, 15000, 30000)):
    """Hypothetical landlord cash costs in one year, not a works estimate.

    Amounts are the unrecovered balance, not a gross building invoice. Never
    infer recovery from a cap or assume the same one-off bill recurs annually.
    """
    if not number(rent) or not number(capital) or capital <= 0:
        return []
    if any(not number(amount) for amount in amounts):
        raise ValueError('Scenario costs must be finite non-negative amounts')
    return [{'unrecovered_cost': rounded(amount),
             'cash_remaining': rounded(rent - amount),
             'cash_return_pct': percent(rent - amount, capital),
             'period': 'Year in which the cost is paid',
             'basis': 'Illustrative unrecovered landlord expenditure, not a repair quotation or forecast. '
                      'Full stated rent assumed collected; excludes other expenses, finance and tax. '
                      'Recovery amounts and timing are not assumed.'}
            for amount in amounts]


def ownership_scenarios(rent, capital, *, principal_rent=None,
                        annual_costs=(5000, 10000), repair=25000,
                        conditional_rent=None):
    """Cash sensitivities, separating recurring expenditure from a one-off bill.

    All amounts are the landlord's *unrecovered* costs. Negative cash survives.
    A conditional rent must carry its condition; it never replaces passing rent.
    """
    if not number(rent) or not number(capital) or capital <= 0:
        return []
    if (not annual_costs or any(not number(v) for v in annual_costs)
            or not number(repair)):
        raise ValueError('Finite non-negative scenario costs are required')
    if principal_rent is not None and (not number(principal_rent) or principal_rent > rent):
        raise ValueError('Principal rent must be reconciled within total rent')
    rows = []
    def add(label, received, recurring=0, one_off=0, period='Illustrative annual cash return'):
        remaining = rounded(received - recurring - one_off)
        rows.append(dict(label=label, rent_received=received,
                         recurring_cost=recurring, one_off_cost=one_off,
                         cash_remaining=remaining, cash_return_pct=percent(remaining, capital),
                         capital=capital, period=period))
    add('Passing rent before ownership costs', rent)
    for cost in annual_costs:
        add(f'£{cost:,.0f} annual unrecovered costs', rent, cost)
    base = annual_costs[0]
    add(f'£{repair:,.0f} one-off repair + £{base:,.0f} annual costs', rent, base, repair,
        'Cash return in the year the repair is paid; not a recurring yield')
    if principal_rent is not None:
        for months in (6, 12):
            add(f'{months}-month main-unit vacancy + £{base:,.0f} annual costs',
                rounded(rent - principal_rent * months / 12), base)
    if conditional_rent is not None:
        if (not number(conditional_rent.get('amount'))
                or not str(conditional_rent.get('condition') or '').strip()):
            raise ValueError('Conditional rent requires an amount and explicit condition')
        add('Conditional rent: ' + conditional_rent['condition'], conditional_rent['amount'], base)
    return rows


def acquisition_price_scenarios(rent, prices, *, fixed_costs, allowances=0,
                                seller_rate=0, seller_vat_rate=0,
                                seller_fixed_costs=0, seller_costs_taxable=False,
                                non_residential_tax=False):
    """Recompute costs and tax at each hypothetical price; never infer a sale.

    Caller must explicitly establish tax classification and seller-cost treatment.
    Allowances remain labelled separately from evidenced transaction charges.
    """
    values = [rent, fixed_costs, allowances, seller_rate, seller_vat_rate, seller_fixed_costs, *prices]
    if any(not number(v) for v in values) or any(p <= 0 for p in prices):
        raise ValueError('Finite non-negative inputs and positive prices are required')
    if seller_rate > 1 or seller_vat_rate > 1:
        raise ValueError('Rates must be fractions between zero and one')
    rows = []
    for price in prices:
        seller = rounded(rounded(price * seller_rate) * (1 + seller_vat_rate) + seller_fixed_costs)
        consideration = rounded(price + (seller if seller_costs_taxable else 0))
        tax = non_residential_sdlt(consideration) if non_residential_tax else None
        capital = rounded(price + fixed_costs + allowances + seller + (tax or 0))
        rows.append(dict(price=price, fixed_costs=fixed_costs, allowances=allowances,
                         seller_costs=seller, tax=tax, tax_consideration=consideration,
                         capital=capital, gross_yield_pct=percent(rent, price),
                         gross_return_on_capital_pct=percent(rent, capital),
                         basis='Illustrative price, not an achieved price or valuation'))
    return rows


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
    capital = rounded((subtotal or price)+tax['amount']) if price is not None and tax else subtotal or price
    # Every return on expenditure uses the same identified acquisition total,
    # including the explicitly illustrative tax. Unknown costs remain excluded,
    # not zero. The purchase-price yield remains a separate headline measure.
    denominator = capital
    for scenario in scenarios:
        scenario['return_pct'] = percent(scenario['cash_before_finance_tax'], capital)
    loss_cases, capacity = investment_exposure(report, principal, rent, capital)
    from acquisition_operating_costs import observed_management, return_headroom
    management = observed_management(inv.get('evidence', []), rent)
    after_management_capacity = return_headroom(rent, capital, management['annualised_management']) if management else []
    return {'price': price, 'rent': rent, 'fixed_fees': fixed, 'known_subtotal': subtotal, 'illustrative_tax':tax,
            'denominator': denominator,
            'denominator_basis': ('price plus quantified fees' if subtotal else 'price; fees are not established') + (' and illustrative purchase tax' if tax else '; purchase tax is unpriced'),
            'gross_return_on_identified_capital_pct': percent(rent, capital) if rent is not None else None,
            'principal': principal, 'income_reconciled': reconciled,
            'scenarios': scenarios, 'price_rows': price_rows,
            'rent_loss_cases': loss_cases, 'cost_capacity': capacity,
            'management_illustration': management,
            'cost_capacity_after_management': after_management_capacity,
            'unrecovered_cost_scenarios': unrecovered_cost_scenarios(rent, capital),
            'capital_basis': capital, 'historical_costs': historical_costs(report),
            'unknown_costs': unknown_costs,
            'costs_complete': False}
