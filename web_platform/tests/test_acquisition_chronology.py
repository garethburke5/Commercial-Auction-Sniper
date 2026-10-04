from acquisition_chronology import lease_chronology
from acquisition_intelligence import build_acquisition, snapshot
from acquisition_report import render


def model():
    return {'created_at':'2026-10-04','property':'1 High Street','report_id':'chronology', 'coverage':{},'missing':[],
            'documents':[{'document':'2012.09.14 Lease.pdf','type':'lease','pages':20}, {'document':'Completed Lease.pdf','type':'lease','pages':15}], 'findings':[]}


def fact(name,title,summary,excerpt):
    return {'title':title,'summary':summary,'fact':True,'topic':'rent','action':'Check the operative lease','evidence':[{'document':name,'page':2,'excerpt':excerpt}]}


def test_age_does_not_mean_historic_or_superseded_and_ocr_does_not_create_dates():
    m=model();m['findings']=[fact('Completed Lease.pdf','Lease term recorded','Five years. Scanned dates need visual confirmation.','from 24 May 2023 to and including 23 May 2028')]
    docs,records=lease_chronology(m)
    assert docs[0]['document_date']=='2012-09-14'
    assert all(d['temporal_status']=='CONTINUING EFFECT UNCONFIRMED' for d in docs)
    assert records[1]['term_start'] is None


def test_alterations_licence_is_supporting_evidence_not_an_occupational_lease():
    m=model();m['documents'].append({'document':'2012.09.14 Licence For Alts.pdf.pdf','type':'lease'})
    docs,records=lease_chronology(m)
    assert len(records)==2
    assert docs[-1]['type']=='licence for alterations' and docs[-1]['temporal_status']=='SUPPORTING'


def test_exact_explicit_terms_are_dated_without_claiming_current_occupation():
    m=model();m['findings']=[fact('Completed Lease.pdf','Lease term recorded','Term from 24 May 2023 to 23 May 2028','from and including 24 May 2023 to and including 23 May 2028')]
    docs,records=lease_chronology(m)
    assert records[1]['term_start']=='2023-05-24' and records[1]['term_end']=='2028-05-23'
    assert 'COVERS REVIEW DATE' in docs[1]['temporal_status']
    m['created_at']='2029-01-01'
    assert 'HOLDING OVER UNCONFIRMED' in lease_chronology(m)[0][1]['temporal_status']


def test_cross_document_rents_are_not_promoted_to_current_income_or_free_payload():
    m=model();m['findings']=[fact('2012.09.14 Lease.pdf','Rent amount recorded in this document','£50,000 per annum','annual rent £50,000 per annum'),fact('Completed Lease.pdf','Rent amount recorded in this document','£35,000 per annum','annual rent £35,000 per annum')]
    report=build_acquisition(m,{'guide':250000})
    assert report['rent'] is None
    assert not any(c['label']=='Gross Initial Yield (GIY)' for c in report['calculations'])
    assert any(f['id']=='lease-rent-chronology' for f in report['findings'])
    assert len(report['lease_reconciliation'])==2
    assert 'lease_reconciliation' not in snapshot(report)
    assert 'Rent in this document' in render(report)
