import copy
import pytest
from acquisition_intelligence import build_acquisition,snapshot
from acquisition_evidence_graph import reasoning_packet,validate_open_review,validate_external_research
from acquisition_quality import paid_report_status
from acquisition_energy import identifiers
from acquisition_reasoning import run_open_review
from acquisition_transcription import apply_transcriptions
from legal_pack_engine import make_document,DocType,classify_document
from legal_pack_service import analyse_uploaded_pack


def model():
    lease={'document':'Lease 1 Main Street.pdf','interest':'Occupational lease / confirm interest','annual_rent':20000,'term':{'text':'a term of FIVE years','uncertain':False},'tenant':'A Tenant','breaks':[], 'evidence':[{'document':'Lease 1 Main Street.pdf','page':1,'excerpt':'Annual Rent £20,000','document_sha256':'abc'}]}
    return {'property':'1 Main Street, Town','report_id':'test','created_at':'2026-10-07','findings':[], 'lease_details':[lease],'transaction_findings':[], 'documents':[{'document':lease['document'],'type':'lease','sha256':'abc','pages':2}],'coverage':{},'missing':[]}

def cat(**kw):return dict(address='1 Main Street, Town',guide=200000,rent=20000,tenure='Freehold',country='England',**kw)

def external(kind,quote='source evidence',**kw):
    return {'sources':[{'id':'s','url':'https://example.org/source','title':'Source','observed_at':'2026-10-07','text':quote}], 'records':[dict(id='r',source_id='s',subject='1 Main Street, Town',kind=kind,quote=quote,**kw)]}


def test_no_hidden_paid_launch_approval_or_private_snapshot():
    r=build_acquisition(model(),cat());assert not paid_report_status({'approved':True})['purchase_available']
    s=snapshot(r)
    assert not {'investigation','amendment_review','source_pages','report_media'} & s.keys()
    assert not s['quality_status']['purchase_available']
    assert not run_open_review(r)['completed']


def test_nearby_development_is_not_subject_development():
    r=build_acquisition(model(),cat(description='Adjacent shopping centre undergoing major redevelopment'))
    assert not r['investigation']['profile']['development']
    assert 'development-deliverability' not in {f['id'] for f in r['investigation']['findings']}


def test_epc_for_other_unit_cannot_close_subject_gap():
    research=external('epc_certificate',demise_document='Lease 2 Main Street.pdf',rating='D',valid_until='2033-01-01')
    r=build_acquisition(model(),cat(),research=research)
    assert any(f['topic']=='energy' for f in r['investigation']['findings'])
    assert r['investigation']['demises'][0]['epc'] is None


def test_epc_expiry_and_jurisdiction_are_not_assumed():
    c=cat();c['country']='Scotland'
    r=build_acquisition(model(),c,research=external('epc_certificate',demise_document='Lease 1 Main Street.pdf',rating='F',valid_until='2020-01-01'))
    assert any(f['id'].startswith('epc-expired') for f in r['investigation']['findings'])
    r2=build_acquisition(model(),c)
    assert 'April 2018' not in ' '.join(f['finding'] for f in r2['investigation']['findings'])


def test_asking_price_is_not_valuation_or_achieved_comparable():
    r=build_acquisition(model(),cat(),research=external('subject_asking_sale','The asking price is £265,000.',price=265000,price_basis='asking'))
    m=r['investigation']['market'];assert m['valuation'] is None and m['maximum_bid'] is None
    assert m['price_support']=='inconclusive'
    assert len(m['records'])==1


def test_numeric_assertion_must_match_source_not_just_quote():
    r=external('subject_asking_sale','The asking price is £265,000.',price=999000)
    assert not validate_external_research(r)['records']


def test_empty_search_does_not_establish_non_compliance():
    r=build_acquisition(model(),cat(description='Grade II Listed'),research=external('epc_search',demise_document='Lease 1 Main Street.pdf',result_summary='No results for this exact address search.'))
    f=next(f for f in r['investigation']['findings'] if f['topic']=='energy')
    assert f['state']=='missing' and 'no breach' in f['consequence']
    assert 'not an automatic exemption' in f['finding']


def test_quote_tampering_rejected():
    research=external('sale_comparable');research['records'][0]['quote']='invented achieved sale'
    assert not validate_external_research(research)['records']


def test_review_can_surface_unanticipated_issue_without_new_rule():
    r=build_acquisition(model(),cat());p=reasoning_packet(r,r['investigation']);ids=[s['id'] for s in p['sources']]
    response={'reviewer':'test reasoning backend','evidence_digest':p['evidence_digest'],'reviewed_source_ids':ids,'unreviewed_source_ids':[], 'findings':[{'id':'unanticipated','title':'Unusual disposal condition','state':'unresolved','materiality':'decision_gate','evidence_ids':ids[:1],'finding':'A condition needs assessment','consequence':'May restrict disposal','resolution':'Check the operative deed','reasoning':'The evidenced condition interacts with disposal.'}]}
    reviewed=validate_open_review(response,p)
    assert reviewed['completed'] and reviewed['findings'][0]['id']=='unanticipated'
    assert not reviewed['investment_approved']
    response['evidence_digest']='wrong';assert not validate_open_review(response,p)['provenance_valid']


def test_missing_review_coverage_cannot_be_marked_complete():
    r=build_acquisition(model(),cat());p=reasoning_packet(r,r['investigation'])
    response={'reviewer':'reviewer','evidence_digest':p['evidence_digest'],'reviewed_source_ids':[],'unreviewed_source_ids':[],'findings':[]}
    assert not validate_open_review(response,p)['completed']


@pytest.mark.parametrize('name',['Licence for Alterations.pdf','Schedule of Dilapidations.pdf','Title information.pdf','Commercial - 15th July 2026 - Lot 87 - Unit 5.pdf'])
def test_supporting_documents_do_not_become_leases(name):
    assert classify_document(name,'Lease Tenant Annual Rent £50000')!=DocType.LEASE


def test_explicit_cost_amendment_replaces_only_seller_allocation():
    quote='In the Special Conditions of Sale, the following amendments apply: the Buyer shall reimburse the Seller the costs of disbursements being £2,000 plus VAT and £100 towards the legal fees.'
    r=build_acquisition(model(),dict(cat(),auctioneer_fee=1800),research=external('auction_addendum',quote))
    assert sum(c['amount'] for c in r['costs'])==4300
    assert any('VAT treatment' in c['basis'] for c in r['costs'])


def test_wrong_property_amendment_cannot_change_costs():
    rs=external('auction_addendum','following amendments apply costs of disbursements being £2,000 plus VAT and £100 towards the legal fees')
    rs['records'][0]['subject']='2 Other Street'
    r=build_acquisition(model(),cat(),research=rs);assert r['costs']==[]


def test_visual_correction_needs_exact_document_and_page():
    d=make_document('Lease.pdf','24 Ju1y 2013',raw=b'original PDF',metadata={'pages':[{'page':1,'text':'24 Ju1y 2013'}]})
    fix={'document':d.name,'document_sha256':d.sha256,'page':1,'before':'24 Ju1y 2013','after':'24 July 2013','reviewer':'reviewer','reviewed_at':'2026-10-07','reason':'Visual source checked'}
    out=apply_transcriptions([d],[fix]);assert out[0].text=='24 July 2013' and d.text=='24 Ju1y 2013'
    fix['document_sha256']='wrong'
    with pytest.raises(ValueError):apply_transcriptions([d],[fix])


def test_address_identity_never_matches_on_postcode_alone():
    assert identifiers('1 Main Street, AA1 1AA') & identifiers('1 Main Street, AA2 2BB')
    assert not identifiers('1 Main Street, AA1 1AA') & identifiers('2 Main Street, AA1 1AA')


def test_per_demise_income_downside_uses_actual_exposure():
    r=build_acquisition(model(),cat());rows=r['investigation']['scenarios']
    assert [(x['rent'],x['yield']) for x in rows]==[(20000,10.0),(10000,5.0),(0,0.0)]


def test_multiple_lease_versions_do_not_establish_multi_let_investment():
    m=model();old=copy.deepcopy(m['lease_details'][0]);old.update(document='Old Lease.pdf',annual_rent=30000)
    m['lease_details'].append(old)
    r=build_acquisition(m,cat())
    assert not r['investigation']['income_reconciled']
    assert r['investigation']['profile']['multi_let'] is None


def test_checkout_cannot_be_enabled_by_provider_configuration():
    from fastapi import HTTPException
    from web_platform.billing import Billing
    billing=Billing(None,'configured','configured',{},'https://example.org',{'legal_pack_report':'price_configured'})
    with pytest.raises(HTTPException) as error:
        billing.purchase('user','legal_pack_report','review:test')
    assert error.value.status_code==503 and 'quality' in error.value.detail


def test_banked_market_context_enters_brief_without_becoming_verified_valuation():
    from acquisition_presentation import make_brief
    c=cat();c['market_context']={'comparables':[{'address':'3 Main Street','url':'https://example.org/lot','guide_price':175000,'auction_date':'2025-01-01','source':'Auctioneer','status':'unsold'}]}
    r=build_acquisition(model(),c)
    assert r['investigation']['market']['records'][0]['price_basis']=='guide'
    assert r['investigation']['market']['valuation'] is None
    assert '175,000' in str(make_brief(r))


def test_uploaded_pack_invokes_full_source_reasoning_backend():
    from io import BytesIO
    from docx import Document
    doc=Document();doc.add_paragraph('The unusual consent affects assignment of this lease.')
    stream=BytesIO();doc.save(stream)
    def backend(packet):
        evidence=[s['id'] for s in packet['sources'] if 'unusual consent' in (s.get('text') or s.get('excerpt',''))]
        assert evidence
        return {'reviewer':'source reviewer','evidence_digest':packet['evidence_digest'],
                'reviewed_source_ids':[s['id'] for s in packet['sources']], 'unreviewed_source_ids':[],
                'findings':[{'id':'assignment-consent','title':'Unusual assignment consent','state':'unresolved',
                    'materiality':'price_sensitive','evidence_ids':evidence,'finding':'Consent affects assignment.',
                    'consequence':'Disposal may depend on consent.','resolution':'Review the operative restriction.',
                    'reasoning':'The source restriction connects to exit liquidity.'}]}
    r=analyse_uploaded_pack('1 Main Street, Town',[('Lease.docx',stream.getvalue())],cat(),reasoning_backend=backend)['acquisition']
    assert any(f['id']=='assignment-consent' for f in r['investigation']['findings'])
    assert r['investigation']['open_review']['completed']
    assert not r['quality_status']['purchase_available']


def test_pdf_export_remains_owner_purchase_and_refund_bound(tmp_path):
    import json,time
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web_platform.accounts import Accounts
    from web_platform.workspace import initialise
    from web_platform.review_api import install
    accounts=Accounts(tmp_path/'reports.sqlite');initialise(accounts)
    report=build_acquisition(model(),cat())
    with accounts.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r','alice','p',json.dumps(report),int(time.time())))
    app=FastAPI();install(app,SimpleNamespace(),lambda header:(header,accounts,None))
    url='/api/account/reviews/r/download?format=pdf'
    with TestClient(app) as client:
        assert client.get(url,headers={'Authorization':'bob'}).status_code==404
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403
        with accounts.db() as db:
            db.execute("INSERT INTO purchases(order_id,user_id,product,property_id,price_id,status,created_at) VALUES ('o','alice','legal_pack_report','review:r','price','paid_awaiting_fulfilment',?)",(int(time.time()),))
        response=client.get(url,headers={'Authorization':'alice'})
        assert response.status_code==200 and response.content.startswith(b'%PDF')
        assert response.headers['cache-control']=='no-store'
        with accounts.db() as db:db.execute("UPDATE purchases SET status='refund_review'")
        assert client.get(url,headers={'Authorization':'alice'}).status_code==403
