"""Audited visual corrections, bound to exact PDF bytes and page text."""
from copy import deepcopy


def apply_transcriptions(documents, corrections=()):
    documents = deepcopy(list(documents))
    for fix in corrections or ():
        if not fix.get('reviewer') or not fix.get('reviewed_at') or not fix.get('reason'):
            raise ValueError('Visual correction needs reviewer, date and reason')
        matches=[d for d in documents if d.sha256==fix.get('document_sha256') and d.name==fix.get('document')]
        if len(matches)!=1:raise ValueError('Visual correction does not match one exact document')
        d=matches[0];pages=[p for p in d.metadata.get('pages',[]) if p.get('page')==fix.get('page')]
        if len(pages)!=1 or not fix.get('before') or pages[0]['text'].count(fix['before'])!=1:
            raise ValueError('Visual correction does not match one exact page excerpt')
        p=pages[0];p.setdefault('original_text',p['text'])
        p['text']=p['text'].replace(fix['before'],fix['after'],1)
        d.metadata.setdefault('visual_transcriptions',[]).append(dict(fix))
        d.text='\n\n'.join(p.get('text','') for p in d.metadata['pages'])
    return documents


def validate_visual_dispositions(model, records):
    expected={(d.get('sha256'),p) for d in model.get('documents',[]) for p in d.get('unread_pages',[])}
    valid=[]
    for r in records:
        if (r.get('document_sha256'),r.get('page')) not in expected:
            raise ValueError('Visual disposition does not match an unread source page')
        if r.get('disposition') not in ('blank','divider','plan_reviewed','unresolved') or not all(r.get(k) for k in ('reviewer','reviewed_at','note')):
            raise ValueError('Incomplete visual disposition')
        valid.append(dict(r))
    resolved={(r['document_sha256'],r['page']) for r in valid if r['disposition']!='unresolved'}
    return {'visual_dispositions':valid,'visual_review_complete':expected <= resolved}
