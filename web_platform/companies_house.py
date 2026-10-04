"""Official company evidence, exact tenant identity, never a manufactured rating."""
import re,os
from datetime import datetime,timezone
import requests

def company_evidence(number,tenant,session=None):
    if not re.fullmatch(r'(?:\d{8}|[A-Z]{2}\d{6})',str(number or '')):return {'status':'identity_unconfirmed','interpretation':'No exact company number established.'}
    key=os.environ.get('COMPANIES_HOUSE_API_KEY')
    if not key:return {'status':'not_configured','interpretation':'Live Companies House checks are not connected. Review the official company record; no financial-strength rating has been assigned.'}
    s=session or requests.Session();base='https://api.company-information.service.gov.uk/company/'+number
    def get(path):
        r=s.get(base+path,auth=(key,''),timeout=15);r.raise_for_status();return r.json()
    profile=get('');normal=lambda x:re.sub(r'[^A-Z0-9]','',str(x).upper().replace('LIMITED','LTD'))
    if normal(profile.get('company_name'))!=normal(tenant):return {'status':'name_mismatch','interpretation':'The company number and named tenant do not match exactly. No covenant assessment is made.'}
    charges=get('/charges');filings=get('/filing-history?items_per_page=10')
    return {'status':'verified_identity','company_name':profile['company_name'],'company_number':number,'company_status':profile.get('company_status'),'accounts':profile.get('accounts'),
        'outstanding_in_returned_records':sum(x.get('status')=='outstanding' for x in charges.get('items',[])),'filings':[{'type':x.get('type'),'date':x.get('date'),'description':x.get('description')} for x in filings.get('items',[])],
        'checked_at':datetime.now(timezone.utc).isoformat(),'source':base,
        'interpretation':f"The exact legal tenant is recorded as {profile.get('company_status','status unknown')} at Companies House. Published accounts and charges are dated evidence; registration status and the presence of security do not establish ability to pay rent. No parent guarantee or credit rating is inferred."}
