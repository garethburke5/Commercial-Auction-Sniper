from copy import deepcopy
from acquisition_public_terms import reconcile_published_inputs, published_terms
from acquisition_evidence_graph import validate_external_research
from collectors.core import Lot
from collectors.savills_all_future import _enhance_savills_lot

TEXT=('The ground floor and basement is let to Example Retail Limited on a 15 year lease expiring 03.08.2040. '
      'The current rent payable is £38,000 per annum, with a fixed uplift to £42,000 in 2028. '
      'The Vendor will "top up" the rent from completion. The upper parts are sold off on a long leasehold basis. '
      'Additional information Tenure Freehold Rent £42,000 per annum')

def inputs():
    cat={'address':'8 Example Street','url':'https://example.org/lot/8','annual_rent':42000,'rent':42000,
         'tenure':'Long Leasehold','collected_at':'2026-10-18'}
    source={'id':'s','url':cat['url'],'observed_at':'2026-10-18','text':TEXT}
    records=[{'id':'r','source_id':'s','subject':cat['address'],'kind':'subject_particulars',
              'quote':TEXT,'field':'annual_rent','basis':'passing_annual','value':38000,'rent':38000},
             {'id':'t','source_id':'s','subject':cat['address'],'kind':'subject_particulars',
              'quote':TEXT,'field':'tenure','value':'Freehold'},
             {'id':'p','source_id':'s','subject':cat['address'],'kind':'subject_particulars',
              'quote':TEXT,'field':'published_particulars','scope':'whole_property'}]
    return cat,{'sources':[source],'records':records}

def test_reconciles_explicit_current_amount_and_freehold_without_mutating_inputs():
    cat,research=inputs();original=deepcopy(cat)
    c=reconcile_published_inputs(cat,research)
    assert c['annual_rent']==c['rent']==38000 and c['tenure']=='Freehold'
    assert len(c['published_input_corrections'])==2 and cat==original
    records=validate_external_research(research)['records']
    terms=published_terms({'property':cat['address'],'investigation':{'external_research':{'records':records}}})
    assert (terms['passing'],terms['headline'],terms['top_up'])==(38000,42000,4000)
    assert terms['upper_parts_sold'] and terms['tenant']=='Example Retail Limited'

def test_other_lot_older_capture_and_unquoted_numbers_cannot_correct_catalogue():
    for change in ('subject','source','date','number'):
        cat,research=inputs()
        if change=='subject':
            for r in research['records']:r['subject']='9 Example Street'
        if change=='source':research['sources'][0]['url']='https://example.org/lot/9'
        if change=='date':research['sources'][0]['observed_at']='2026-10-17'
        if change=='number':research['records'][0].update(value=40000,rent=40000)
        c=reconcile_published_inputs(cat,research)
        assert c['annual_rent']==42000
        if change!='number':assert c['tenure']=='Long Leasehold'

def test_marketing_does_not_become_a_certificate_or_an_exact_break_date():
    cat,research=inputs()
    q='8 Example Street: a tenant break at the 10th year) from 4th August 2025. EPC: C|54.'
    research['sources'].append({'id':'b','url':'https://agent.example/brochure','text':q,'observed_at':'2026-10-18'})
    research['records'] += [dict(id='b',source_id='b',subject=cat['address'],kind='published_lease_terms',unit='8 Example Street',quote=q),
                            dict(id='e',source_id='b',subject=cat['address'],kind='epc_marketing',rating='C',score=54,quote=q)]
    terms=published_terms({'property':cat['address'],'investigation':{'external_research':validate_external_research(research)}})
    assert terms['break_year']==2035 and 'break_date' not in terms
    assert terms['energy'][0]['rating']=='C'
    assert 'certificate_valid' not in terms['energy'][0]

def test_savills_enrichment_keeps_current_rent_and_the_sale_tenure():
    lot=Lot(source='Savills Auctions',url='https://example.org/lot/8',address='8 Example Street',
            tenure='Freehold',annual_rent=38000,guide_price=400000,description=TEXT)
    lot=_enhance_savills_lot(lot)
    assert lot.annual_rent==38000 and lot.tenure=='Freehold' and lot.gross_yield==9.5
