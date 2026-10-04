"""Owner-scoped customer routes. Existing JWT and billing adapters remain authoritative."""
import json,time,re
from typing import Annotated
from fastapi import Header,HTTPException
from pydantic import BaseModel,Field
from . import workspace

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
        if not row:raise HTTPException(404,'Unknown property')
        return workspace.update(a,uid,pid,body.model_dump(exclude_unset=True),row)
    @app.put('/api/account/searches/{sid}')
    def save_search(sid:str,body:Search,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);workspace.initialise(a)
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',sid):raise HTTPException(400,'Invalid search ID')
        from urllib.parse import parse_qsl,urlencode
        allowed={'q','source','min','max','yield','status','tenure','sort'}
        query=urlencode([(k,v) for k,v in parse_qsl(body.query) if k in allowed])
        with a.db() as db:db.execute('INSERT OR REPLACE INTO saved_searches VALUES (?,?,?,?,?,?)',(uid,sid,body.name,query,int(body.digest),int(time.time())))
        return {'saved':True,'digest_delivery':'not active'}
    @app.delete('/api/account/searches/{sid}')
    def delete_search(sid:str,authorization:str|None=Header(default=None)):
        uid,a,_=user(authorization);workspace.initialise(a)
        with a.db() as db:db.execute('DELETE FROM saved_searches WHERE user_id=? AND search_id=?',(uid,sid))
        return {'removed':True}
