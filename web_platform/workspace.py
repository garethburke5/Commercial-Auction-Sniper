"""Private customer workspace, extending the existing verified identity store."""
import json,time,hashlib
from fastapi import HTTPException

FIELDS=('guide_price','guide_price_upper','auction_date','status','legal_pack_url','addendum','annual_rent','tenant','lease_expiry','tenure','occupation')
LABELS={'guide_price':'Guide price','guide_price_upper':'Upper guide','auction_date':'Auction date','status':'Status','legal_pack_url':'Legal pack','addendum':'Addendum','annual_rent':'Current rent','tenant':'Tenant','lease_expiry':'Lease expiry','tenure':'Tenure','occupation':'Occupation'}

def observation(row):
    return {k:row.get(k) for k in FIELDS} | {'id':row['id'],'address':row['address'],'path':row['path'],'source':row.get('source'),
        'image_url':row.get('image_url'),'guide':row.get('guide'),'giy_text':row.get('giy_text'),
        'description_hash':hashlib.sha256(str(row.get('description','')).encode()).hexdigest()[:16]}

def changes(old,new):
    events=[]
    for k in FIELDS:
        if old.get(k)!=new.get(k):
            title=LABELS[k]+' changed'
            if k=='guide_price' and isinstance(old.get(k),(int,float)) and isinstance(new.get(k),(int,float)) and new[k]<old[k]:title='Guide reduced'
            if k=='status':title=str(new[k] or 'Status updated').title()
            if k=='legal_pack_url' and not old.get(k) and new.get(k):title='Legal pack available'
            events.append({'field':k,'title':title,'before':old.get(k),'after':new.get(k)})
    if old.get('description_hash') and old['description_hash']!=new.get('description_hash'):events.append({'field':'particulars','title':'Property particulars updated','before':None,'after':'Read the latest source particulars'})
    return events

def initialise(accounts):
    if accounts.managed_schema:return
    with accounts.db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS workspace(user_id TEXT NOT NULL,property_id TEXT NOT NULL,watched INTEGER NOT NULL DEFAULT 0,notes TEXT NOT NULL DEFAULT '',target_price REAL,observation TEXT,updated_at INTEGER NOT NULL,PRIMARY KEY(user_id,property_id));
        CREATE TABLE IF NOT EXISTS saved_searches(user_id TEXT NOT NULL,search_id TEXT NOT NULL,name TEXT NOT NULL,query TEXT NOT NULL,digest INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,PRIMARY KEY(user_id,search_id));
        CREATE TABLE IF NOT EXISTS watch_events(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,property_id TEXT NOT NULL,event_json TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,property_id TEXT NOT NULL,report_json TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS review_processing(review_id TEXT PRIMARY KEY,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,updated_at INTEGER NOT NULL);
        ''')

def update(accounts,user,pid,body,row):
    # Enforce in the service as well as the UI: no direct API or import bypass.
    # A former subscriber can always stop a watch or clear their own data.
    if body.get('watched'): accounts.require(user,'watch')
    if body.get('notes'): accounts.require(user,'notes')
    if body.get('target_price') is not None: accounts.require(user,'bid_targets')
    initialise(accounts)
    if len(body.get('notes',''))>10000:raise HTTPException(400,'Note exceeds 10,000 characters')
    with accounts.db() as db:
        old=db.execute('SELECT * FROM workspace WHERE user_id=? AND property_id=?',(user,pid)).fetchone()
        entry=dict(old) if old else {'watched':0,'notes':'','target_price':None,'observation':None}
        for k in ('watched','notes','target_price'):
            if k in body:entry[k]=body[k]
        if entry['watched'] and not entry['observation']:entry['observation']=json.dumps(observation(row))
        if not entry['watched']:entry['observation']=None
        db.execute('''INSERT INTO workspace VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id,property_id)
            DO UPDATE SET watched=excluded.watched,notes=excluded.notes,target_price=excluded.target_price,
            observation=excluded.observation,updated_at=excluded.updated_at''',
            (user,pid,int(entry['watched']),entry['notes'],entry['target_price'],entry['observation'],int(time.time())))
    return {'updated':True}

def dashboard(accounts,user,rows,*,monitoring_rows=None):
    initialise(accounts)
    from .plans import ENTITLEMENTS
    monitoring = 'watch' in ENTITLEMENTS[accounts.plan(user)]
    observed_rows = rows if monitoring_rows is None else monitoring_rows
    with accounts.db() as db:
        items=[dict(r) for r in db.execute('SELECT * FROM workspace WHERE user_id=?',(user,))]
        for item in items:
            pid=item['property_id'];row=rows.get(pid)
            observed=observed_rows.get(pid)
            if monitoring and item['watched'] and observed:
                current=observation(observed);old=json.loads(item['observation'] or '{}')
                for event in changes(old,current):
                    eid=hashlib.sha256(json.dumps([user,pid,old,current,event],sort_keys=True).encode()).hexdigest()
                    db.execute('INSERT INTO watch_events VALUES (?,?,?,?,?) ON CONFLICT(id) DO NOTHING',(eid,user,pid,json.dumps(event),int(time.time())))
                db.execute('UPDATE workspace SET observation=? WHERE user_id=? AND property_id=?',(json.dumps(current),user,pid))
            item.pop('user_id');item.pop('observation',None)
            item['property']=observation(row) if row else None
        events=[dict(r) for r in db.execute('SELECT property_id,event_json,created_at FROM watch_events WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(user,))]
        for e in events:
            e.update(json.loads(e.pop('event_json')))
            if rows.get(e['property_id']):e['property']=observation(rows[e['property_id']])
        searches=[dict(r) for r in db.execute('SELECT search_id,name,query,digest,created_at FROM saved_searches WHERE user_id=? ORDER BY created_at DESC',(user,))]
        reviews=[dict(r) for r in db.execute('SELECT id,property_id,created_at FROM reviews WHERE user_id=? ORDER BY created_at DESC',(user,))]
    return {'properties':items,'events':events,'saved_searches':searches,'reviews':reviews,'monitoring_enabled':monitoring}

def full_review_allowed(accounts,user,report_id,property_id):
    with accounts.db() as db:
        # Payment is bound to THIS report, not every future pack for this address.
        return bool(db.execute("SELECT 1 FROM purchases WHERE user_id=? AND product='legal_pack_report' AND property_id=? AND status='paid_awaiting_fulfilment'",(user,'review:'+report_id)).fetchone())
