"""Owner-scoped customer routes. Existing JWT and billing adapters remain authoritative."""
import json,time,re
from typing import Annotated
from fastapi import Header,HTTPException
from pydantic import BaseModel,Field
from . import workspace
from .database import begin_write
from .search_monitoring import clear_search_state

class WorkspaceUpdate(BaseModel):
    watched:bool=False
    notes:str=Field(default='',max_length=10000)
    target_price:float|None=Field(default=None,ge=0,le=1e10,allow_inf_nan=False)
class Search(BaseModel):
    name:str=Field(min_length=1,max_length=160)
    query:str=Field(max_length=2000)
    digest:bool=False

def install(app,site,user):
    @app.put('/api/account/workspace/{pid}')
    def update_workspace(pid:str,body:WorkspaceUpdate,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization)
        from .deals import workspace_rows
        row=site.catalogue.rows.get(pid) or workspace_rows(a).get(pid)
        patch=body.model_dump(exclude_unset=True)
        if not row:
            # Removing a listing must not prevent its owner stopping a watch or
            # clearing private notes after cancellation. Never create an orphan.
            workspace.initialise(a)
            with a.db() as db:
                existing=db.execute('SELECT 1 FROM workspace WHERE user_id=? AND property_id=?',(uid,pid)).fetchone()
            clearing=bool(patch) and all(
                (k=='watched' and v is False) or (k=='notes' and v=='') or
                (k=='target_price' and v is None) for k,v in patch.items())
            if not existing or not clearing:raise HTTPException(404,'Unknown property')
        return workspace.update(a,uid,pid,patch,row)
    @app.put('/api/account/searches/{sid}')
    def save_search(sid:str,body:Search,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);a.require(uid,'saved_searches');workspace.initialise(a)
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',sid):raise HTTPException(400,'Invalid search ID')
        from urllib.parse import parse_qsl,urlencode
        allowed={'q','source','min','max','yield','status','tenure','sort'}
        query=urlencode([(k,v) for k,v in parse_qsl(body.query) if k in allowed])
        with a.db() as db:
            begin_write(db)
            previous=db.execute('SELECT query FROM saved_searches WHERE user_id=? AND search_id=?',(uid,sid)).fetchone()
            if previous and previous['query']!=query:clear_search_state(db,uid,sid)
            db.execute('''INSERT INTO saved_searches VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,search_id)
            DO UPDATE SET name=excluded.name,query=excluded.query,digest=excluded.digest,created_at=excluded.created_at''',
            (uid,sid,body.name,query,int(body.digest),int(time.time())))
        return {'saved':True,'digest_delivery':'not active'}
    @app.delete('/api/account/searches/{sid}')
    def delete_search(sid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);workspace.initialise(a)
        with a.db() as db:
            begin_write(db)
            clear_search_state(db,uid,sid)
            db.execute('DELETE FROM saved_searches WHERE user_id=? AND search_id=?',(uid,sid))
        return {'removed':True}
