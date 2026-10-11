"""Cost estimates use a recorded rate card; missing charges never become zero."""
import json,math,os


def estimate_cost(usage,metrics):
    try:
        rates=json.loads(os.getenv('ACQUISITION_COST_RATES_JSON','{}'))
        keys=('input_usd_per_million','cached_input_usd_per_million','output_usd_per_million',
              'search_usd_per_call','processing_gbp_per_second','document_gbp_per_page','usd_to_gbp')
        if rates.get('model')!=usage.get('model') or not rates.get('effective_date'):
            return {'status':'rates_missing','estimated_total_gbp':None}
        if any(type(rates.get(k)) not in (int,float) or not math.isfinite(rates[k]) or rates[k]<0 for k in keys) or rates['usd_to_gbp']<=0:
            return {'status':'rates_incomplete','estimated_total_gbp':None}
        cached=usage.get('cached_input_tokens',0);uncached=max(0,usage['input_tokens']-cached)
        ai_usd=(uncached*rates['input_usd_per_million']+cached*rates['cached_input_usd_per_million']+usage['output_tokens']*rates['output_usd_per_million'])/1_000_000+usage['search_calls']*rates['search_usd_per_call']
        pages=metrics.get('coverage',{}).get('pages')
        complete=usage.get('complete') is True and isinstance(pages,int)
        total=ai_usd*rates['usd_to_gbp']+metrics['elapsed_seconds']*rates['processing_gbp_per_second']+(pages or 0)*rates['document_gbp_per_page']
        return {'status':'estimated' if complete else 'partial_estimate','rate_card':rates,
                'estimated_ai_usd':round(ai_usd,6),'estimated_total_gbp':round(total,6) if complete else None,
                'known_cost_lower_bound_gbp':round(total,6),
                'note':'Measured usage at the recorded rates; reconcile provider invoices. Payment fees, tax and shared overhead are separate.'}
    except (ValueError,TypeError,KeyError):
        return {'status':'rates_invalid','estimated_total_gbp':None}
