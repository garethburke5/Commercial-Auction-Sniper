"""Cost estimates use a recorded rate card; missing charges never become zero."""
import json,math,os


def estimate_cost(usage,metrics):
    try:
        rates=json.loads(os.getenv('ACQUISITION_COST_RATES_JSON','{}'))
        if not isinstance(rates,dict):
            return {'status':'rates_invalid','estimated_total_gbp':None}
        keys=('input_usd_per_million','cached_input_usd_per_million','output_usd_per_million',
              'search_usd_per_call','processing_gbp_per_second','document_gbp_per_page','usd_to_gbp')
        if rates.get('model')!=usage.get('model') or not rates.get('effective_date'):
            return {'status':'rates_missing','estimated_total_gbp':None}
        if any(type(rates.get(k)) not in (int,float) or not math.isfinite(rates[k]) or rates[k]<0 for k in keys) or rates['usd_to_gbp']<=0:
            return {'status':'rates_incomplete','estimated_total_gbp':None}
        counts=[usage.get(k) for k in ('input_tokens','output_tokens','search_calls')]
        cached=usage.get('cached_input_tokens',0)
        elapsed=metrics.get('elapsed_seconds')
        pages=metrics.get('coverage',{}).get('pages')
        if (any(type(n) is not int or n<0 for n in counts+[cached])
                or cached>usage['input_tokens']
                or (elapsed is not None and (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0))
                or (pages is not None and (type(pages) is not int or pages<0))):
            return {'status':'usage_invalid','estimated_total_gbp':None}
        uncached=usage['input_tokens']-cached
        ai_usd=(uncached*rates['input_usd_per_million']+cached*rates['cached_input_usd_per_million']+usage['output_tokens']*rates['output_usd_per_million'])/1_000_000+usage['search_calls']*rates['search_usd_per_call']
        complete=usage.get('complete') is True and pages is not None and elapsed is not None
        total=ai_usd*rates['usd_to_gbp']+(elapsed or 0)*rates['processing_gbp_per_second']+(pages or 0)*rates['document_gbp_per_page']
        return {'status':'estimated' if complete else 'partial_estimate','rate_card':rates,
                'estimated_ai_usd':round(ai_usd,6),'estimated_total_gbp':round(total,6) if complete else None,
                'known_cost_lower_bound_gbp':round(total,6),
                'note':'Measured usage at the recorded rates; reconcile provider invoices. Payment fees, tax and shared overhead are separate.'}
    except (ValueError,TypeError,KeyError,AttributeError):
        return {'status':'rates_invalid','estimated_total_gbp':None}
