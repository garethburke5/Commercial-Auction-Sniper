"""Bounded commercial interpretation of validated, subject-matched public facts.

These observations do not turn a listing into a verified lease or legal pack.
"""
import re
from acquisition_evidence_graph import norm
from acquisition_financials import number, rounded


def public_insights(report):
    records = [r for r in report.get('investigation', {}).get('external_research', {}).get('records', [])
               if norm(r.get('subject')).casefold() == norm(report.get('property')).casefold()]
    observations = []
    for r in records:
        quote = norm(r.get('quote'))
        if (r['kind'] == 'income_concession' and number(r.get('rent'))
                and re.search(r'half rent', quote, re.I)
                and re.search(r"seller.{0,30}top.?up", quote, re.I)):
            annual = r['rent']; half = rounded(annual/2)
            observations.append({'title': 'Headline income includes a seller-funded top-up',
                'finding': f"The advertised £{annual:,.0f} annual income includes a period when the tenant pays half rent. During that period the tenant pays at a rate of £{half:,.0f} a year, with the other £{half:,.0f} depending on money from the seller.",
                'consequence': 'The buyer needs to check when the reduced rent ends and how the seller’s contribution will be paid and protected. It is not all rent being paid by the tenant.',
                'source': r['source'], 'source_record_id': r.get('id'), 'status': 'Published terms; contractual position unverified'})
        if r['kind'] == 'potential_rent' and number(r.get('rent')) and re.search(r'\bERV\b|estimated rental|potential rent', quote, re.I):
            observations.append({'title': 'Potential rent is not current income',
                'finding': f"The agent suggests £{r['rent']:,.0f} annual rent. It is an estimate, not an existing tenancy or achieved letting.",
                'consequence': 'A buyer would need to pay for any work and the empty period before rent starts. This estimate cannot be used to describe a return from current income.',
                'source': r['source'], 'source_record_id': r.get('id'), 'status': 'Marketing estimate'})
    rents = [r for r in records if r['kind'] == 'subject_particulars' and r.get('field') == 'annual_rent'
             and number(r.get('rent')) and r.get('basis') == 'published_annual']
    if len({r['rent'] for r in rents}) > 1:
        observations.append({'title': 'Published income figures differ',
            'finding': 'The auctioneer’s published pages give ' + ' and '.join(f"£{v:,.0f}" for v in sorted({r['rent'] for r in rents})) + ' annual income.',
            'consequence': 'The buyer needs the latest rent schedule and an explanation of the difference before relying on either figure. The difference does not prove that a tenant owes rent.',
            'source': rents[0]['source'], 'additional_sources': [r['source'] for r in rents[1:]], 'status': 'Source discrepancy'})
    observations.extend(catalogue_lease_insights(report))
    observations.extend(occupation_insights(report, records))
    return observations


def occupation_insights(report, records):
    """Interpret explicit whole-property occupation, without parsing UI statuses.

    Only scoped particulars qualify. The full captured page may contain hidden
    alternative statuses and neighbouring lots, so it is deliberately not read.
    """
    results=[]
    rent=report.get('rent')
    vacant=report.get('investigation',{}).get('profile',{}).get('vacant')
    for r in records:
        if r.get('kind')!='subject_particulars' or r.get('field')!='published_particulars' or r.get('scope')!='whole_property':continue
        text=norm(r.get('quote')); finding='';consequence=''
        single=re.search(r'(?:property is |property (?:is )?comprises .*?property is )?fully let to ([A-Za-z][A-Za-z &.,-]*? (?:Limited|Ltd))\b',text,re.I)
        multi=re.search(r'multi-let to (\d+|two|three|four|five|six|seven|eight|nine|ten) tenants',text,re.I)
        if single and number(rent) and rent>0 and not multi and not vacant:
            finding=f"The investment is let to {single[1]}, so one tenant supports the advertised £{rent:,.0f} annual rent."
            expiry=re.search(r'(?:lease )?expiring (\d{2}\.\d{2}\.\d{4})',text,re.I)
            if expiry:
                from datetime import datetime
                try:finding+=' The advertised lease expires on '+datetime.strptime(expiry[1],'%d.%m.%Y').strftime('%d %B %Y').lstrip('0')+'.'
                except ValueError:pass
            unused=re.search(r'(20\d{2}) break (?:option )?(?:not|has not been) exercised',text,re.I)
            if unused:
                finding+=' The auctioneer says the '+unused[1]+' break option was not exercised.'
            consequence='A full year without this tenant would remove the stated rental income. The purchase budget should therefore allow for an empty period and the cost of finding a replacement occupier.'
        elif multi and not vacant:
            finding=f"The property is let to {multi[1].lower()} tenants. This spreads occupancy across several businesses."
            consequence='The individual rents and lease dates determine how much income could be lost at once; the total rent alone cannot show whether one occupier dominates the investment.'
            if re.search(r'co-terminus leaseholds',text,re.I):
                consequence+=' The purchase also involves linked headleases, so ground rent and obligations to the superior landlord belong in the ownership budget.'
        elif vacant and re.search(r'conversion|redevelopment',text,re.I):
            finding='The premises are vacant. The marketing suggests conversion or redevelopment, subject to obtaining the necessary consents.'
            consequence='The investment depends on the achievable use, works budget and time to occupation. A proposed alternative use should not be valued as an approved scheme.'
        if finding:
            results.append({'title':'Occupation and investment exposure','finding':finding,'consequence':consequence,
                'source':r['source'],'source_record_id':r.get('id'),'status':'Published property particulars'})
    return results


def catalogue_lease_insights(report):
    """Read a specifically linked published break and its tenancy-table rent.

    This is public-information analysis, not legal verification. Require a
    subject catalogue source, exact unit link, matching printed rent and a
    complete date. Whole-page keywords or a neighbouring unit never suffice.
    """
    from acquisition_editorial import exact_date
    rows=report.get('tenancy_schedule') or []
    total=report.get('rent')
    if not rows or not number(total) or not total:return []
    sources=[s for s in report.get('investigation',{}).get('evidence',[]) if s.get('source_kind')=='catalogue' and s.get('url')]
    results=[]
    for source in sources:
        text=norm(source.get('excerpt') or source.get('text'))
        for row in rows:
            unit=next((v for k,v in row.items() if k.lower() in ('address','unit','property')),None)
            rents=[v for k,v in row.items() if 'rent' in k.lower() and 'review' not in k.lower()]
            if not unit or len(rents)!=1:continue
            printed=re.fullmatch(r'£\s*([\d,]+(?:\.\d+)?)',str(rents[0]).strip())
            if not printed or str(rents[0]) not in text:continue
            annual=float(printed[1].replace(',',''))
            if not 0<annual<=total:continue
            pattern=r'As to\s+'+re.escape(unit)+r',\s*the lease provides for a tenant option to determine the lease on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})([^.]*\.)'
            match=re.search(pattern,text,re.I)
            if not match:continue
            when=exact_date(match[1])
            if not when:continue
            notice=' At least six months’ written notice is reported.' if re.search(r'(?:6|six) months',match[2],re.I) else ''
            results.append({'title':'A published lease break could remove part of the income',
                'finding':f"The particulars say the tenant of {unit} can end its lease on {when.strftime('%d %B %Y').lstrip('0')}.{notice} That unit accounts for £{annual:,.0f} a year, or {annual/total*100:.1f}% of the advertised rent.",
                'consequence':f"A full year without that rent would leave £{total-annual:,.0f} before costs, assuming all other rents continue. The signed lease and any later changes need checking before relying on the date or conditions.",
                'source':{'title':source.get('document','Auction particulars'),'url':source['url']},
                'status':'Published terms; legal pack not verified','quote':match[0],'unit':unit})
    return results
