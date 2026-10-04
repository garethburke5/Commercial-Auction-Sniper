"""Small owner-managed commercial listing store; no automatic paid endorsement."""
import json,os,time,re,uuid
from datetime import datetime,timezone
from typing import Literal
from pydantic import BaseModel,Field,field_validator
from fastapi import HTTPException,Header,Request
from .workspace import observation

class Deal(BaseModel):
    address:str=Field(min_length=8,max_length=250)
    listing_type:Literal['Private deal','Off-market','Agent / vendor listing','Featured auction','Sponsored']
    status:Literal['Draft','Available','Under offer','Sold','Withdrawn']='Draft'
    price:float|None=Field(default=None,ge=0,le=1e10,allow_inf_nan=False)
    annual_rent:float|None=Field(default=None,ge=0,le=1e10,allow_inf_nan=False)
    area_sqft:float|None=Field(default=None,gt=0,le=1e8,allow_inf_nan=False)
    tenure:str=Field(default='',max_length=100)
    property_type:str=Field(default='',max_length=100)
    tenant:str=Field(default='',max_length=250)
    lease_summary:str=Field(default='',max_length=2000)
    occupancy:Literal['Unknown','Investment','Vacant','Part let']='Unknown'
    vat:str=Field(default='',max_length=500)
    description:str=Field(default='',max_length=12000)
    highlights:list[str]=Field(default_factory=list,max_length=12)
    images:list[str]=Field(default_factory=list,max_length=20)
    documents:list[str]=Field(default_factory=list,max_length=20)
    enquiry_url:str=Field(default='',max_length=2000)
    source_url:str=Field(default='',max_length=2000)
    featured:bool=False
    sponsored:bool=False
    promotion_start:str|None=None
    promotion_end:str|None=None
    expires_at:str|None=None
    version:int=0
    @field_validator('images','documents')
    @classmethod
    def urls(cls,values):
        for v in values:
            if not re.match(r'^https://[^\s<>"\']+$',v):raise ValueError('Use HTTPS image/document URLs')
        return values
    @field_validator('enquiry_url','source_url')
    @classmethod
    def url(cls,v):
        if v and not re.match(r'^https://[^\s<>"\']+$',v):raise ValueError('Use an HTTPS URL')
        return v
    @field_validator('promotion_start','promotion_end','expires_at')
    @classmethod
    def dates(cls,v):
        if v:datetime.fromisoformat(v.replace('Z','+00:00'))
        return v
class Enquiry(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    email:str=Field(min_length=5,max_length=250)
    message:str=Field(min_length=10,max_length=3000)
    consent:bool
    website:str=''
    @field_validator('email')
    @classmethod
    def email_address(cls,v):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('Enter a valid email')
        return v

def initialise(a):
    with a.db() as db:db.executescript('''CREATE TABLE IF NOT EXISTS deals(id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,body TEXT NOT NULL,version INTEGER NOT NULL,updated_at INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS deal_enquiries(id TEXT PRIMARY KEY,deal_id TEXT NOT NULL,name TEXT NOT NULL,email TEXT NOT NULL,message TEXT NOT NULL,created_at INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS deal_metrics(deal_id TEXT NOT NULL,metric TEXT NOT NULL,count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(deal_id,metric));''')
def active(d):
    return d['status'] in ('Available','Under offer') and (not d.get('expires_at') or instant(d['expires_at'])>datetime.now(timezone.utc))
def instant(v):
    dt=datetime.fromisoformat(v.replace('Z','+00:00'))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
def public(d):
    d=dict(d);p=d.get('price');rent=d.get('annual_rent') if d.get('occupancy') in ('Investment','Part let') else None;a=d.get('area_sqft')
    d.update(giy=round(100*rent/p,2) if p and rent else None,price_psf=round(p/a,2) if p and a else None,rent_psf=round(rent/a,2) if rent and a else None)
    now=datetime.now(timezone.utc);promotion=(not d.get('promotion_start') or instant(d['promotion_start'])<=now) and (not d.get('promotion_end') or instant(d['promotion_end'])>=now)
    d['featured']=d.get('featured',False) and promotion;d['sponsored']=d.get('sponsored',False) and promotion
    return d

def workspace_rows(a):
    initialise(a)
    with a.db() as db: records=list(db.execute('SELECT id,body FROM deals'))
    rows={}
    for r in records:
        d=json.loads(r['body'])
        if d['status']=='Draft':continue
        pid='deal:'+r['id']
        rows[pid]=dict(d,id=pid,path='/deals/#deal-'+r['id'],source='Commercial Deals · '+d['listing_type'],
            guide_price=d.get('price'),annual_rent=d.get('annual_rent') if d.get('occupancy') in ('Investment','Part let') else None,
            occupation=d.get('occupancy'),image_url=(d.get('images') or [None])[0])
    return rows

def install(app,site,user,services):
    def admin(authorization):
        uid,a,b=user(authorization)
        if uid not in {x.strip() for x in os.getenv('ADMIN_ACCOUNT_IDS','').split(',') if x.strip()}:raise HTTPException(403,'Owner access required')
        initialise(a);return uid,a,b
    @app.get('/api/deals')
    def list_deals():
        a,_=services();initialise(a)
        with a.db() as db:rows=[json.loads(r['body'])|{'id':r['id'],'version':r['version']} for r in db.execute('SELECT * FROM deals')]
        return {'listings':[public(d) for d in rows if active(d)]}
    @app.get('/api/admin/deals')
    def admin_deals(authorization:str|None=Header(default=None)):
        uid,a,_=admin(authorization)
        with a.db() as db:
            return {'listings':[json.loads(r['body'])|{'id':r['id'],'version':r['version']} for r in db.execute('SELECT * FROM deals WHERE owner_id=?',(uid,))],
                'enquiries':[dict(r) for r in db.execute('SELECT e.* FROM deal_enquiries e JOIN deals d ON e.deal_id=d.id WHERE d.owner_id=? ORDER BY e.created_at DESC',(uid,))],
                'metrics':[dict(r) for r in db.execute('SELECT m.* FROM deal_metrics m JOIN deals d ON m.deal_id=d.id WHERE d.owner_id=?',(uid,))]}
    @app.put('/api/admin/deals/{did}')
    def save_deal(did:str,body:Deal,authorization:str|None=Header(default=None)):
        uid,a,_=admin(authorization)
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',did):raise HTTPException(400,'Invalid listing ID')
        if body.status!='Draft' and (len(body.description)<120 or not body.property_type or not body.enquiry_url):raise HTTPException(400,'Publishing requires substantive particulars, a commercial use type and an enquiry route')
        from collectors.publication_quality import commercial_decision
        if body.status!='Draft' and commercial_decision({'description':body.description,'property_type':body.property_type,'address':body.address}) is not True:raise HTTPException(400,'Particulars must establish a commercial or mixed-use opportunity')
        with a.db() as db:
            db.execute('BEGIN IMMEDIATE');old=db.execute('SELECT owner_id,version FROM deals WHERE id=?',(did,)).fetchone()
            if old and old['owner_id']!=uid:raise HTTPException(404,'Unknown listing')
            if old and body.version!=old['version']:raise HTTPException(409,'Listing changed. Reload before saving.')
            version=(old['version'] if old else 0)+1
            db.execute('INSERT OR REPLACE INTO deals VALUES (?,?,?,?,?)',(did,uid,json.dumps(body.model_dump()),version,int(time.time())))
        return {'id':did,'version':version,'listing':public(body.model_dump()|{'id':did})}
    @app.post('/api/deals/{did}/enquiries')
    def enquire(did:str,body:Enquiry):
        if not body.consent or body.website:raise HTTPException(400,'Enquiry cannot be submitted')
        a,_=services();initialise(a)
        with a.db() as db:
            row=db.execute('SELECT body FROM deals WHERE id=?',(did,)).fetchone()
            if not row or not active(json.loads(row['body'])):raise HTTPException(404,'Listing unavailable')
            if db.execute('SELECT 1 FROM deal_enquiries WHERE email=? AND created_at>?',(body.email,int(time.time())-60)).fetchone():raise HTTPException(429,'Please wait before submitting another enquiry')
            db.execute('INSERT INTO deal_enquiries VALUES (?,?,?,?,?,?)',(uuid.uuid4().hex,did,body.name,body.email,body.message,int(time.time())))
            db.execute("INSERT INTO deal_metrics VALUES (?,'enquiries',1) ON CONFLICT(deal_id,metric) DO UPDATE SET count=count+1",(did,))
        return {'received':True,'message':'Your enquiry is recorded for the listing owner.'}
    @app.post('/api/deals/{did}/view')
    def view(did:str):
        a,_=services();initialise(a)
        with a.db() as db:
            row=db.execute('SELECT body FROM deals WHERE id=?',(did,)).fetchone()
            if not row or not active(json.loads(row['body'])):raise HTTPException(404,'Unknown listing')
            db.execute("INSERT INTO deal_metrics VALUES (?,'detail_views',1) ON CONFLICT(deal_id,metric) DO UPDATE SET count=count+1",(did,))
        return {'recorded':True}
