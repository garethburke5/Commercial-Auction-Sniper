"""Real signed tokens, synthetic session store; no customer credentials."""
import time
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from web_platform import accounts, database


@pytest.fixture
def signed_session(monkeypatch):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuer='https://session-test.example/auth/v1'
    claims={'sub':str(uuid4()),'session_id':str(uuid4()),'iss':issuer,
            'aud':'authenticated','iat':int(time.time()),'exp':int(time.time())+300}
    monkeypatch.setenv('AUTH_ISSUER',issuer)
    monkeypatch.setenv('ACCOUNT_DATABASE_URL','postgresql://synthetic/session_test')
    monkeypatch.setattr(accounts,'key_client',lambda _:SimpleNamespace(
        get_signing_key_from_jwt=lambda _:SimpleNamespace(key=key.public_key())))
    return claims,lambda c:jwt.encode(c,key,algorithm='RS256')


def test_signed_token_is_rechecked_after_revocation_and_bound_to_subject(signed_session,monkeypatch):
    claims,sign=signed_session
    active={(claims['session_id'],claims['sub'])}
    lookups=[]
    class DB:
        def execute(self,sql,params=()):
            if sql.startswith('SET '):return None
            lookups.append(params)
            return SimpleNamespace(fetchone=lambda:(1,) if params in active else None)
    @contextmanager
    def connect(_):yield DB()
    monkeypatch.setattr(database,'connect_postgres',connect)
    token=sign(claims)
    user=accounts.authenticated_user('Bearer '+token)
    active.clear()
    with pytest.raises(HTTPException) as error:accounts.authenticated_user('Bearer '+token)
    assert error.value.status_code==401
    # Another user's active session cannot validate this token's subject.
    active.add((claims['session_id'],str(uuid4())))
    with pytest.raises(HTTPException) as error:accounts.authenticated_user('Bearer '+token)
    assert error.value.status_code==401
    # A fresh legitimate login retains the same account and purchased records.
    renewed=dict(claims,session_id=str(uuid4()))
    active.add((renewed['session_id'],renewed['sub']))
    assert accounts.authenticated_user('Bearer '+sign(renewed))==user
    assert len(lookups)==4


@pytest.mark.parametrize('change',[{'session_id':None},{'session_id':''},{'session_id':42},
                                  {'session_id':'not-a-uuid'},{'sub':{}},{'is_anonymous':True},
                                  {'exp':1},{'iss':'https://attacker.example'},
                                  {'aud':'anon'},{'session_id':['invalid']}])
def test_invalid_tokens_never_query_private_sessions(signed_session,monkeypatch,change):
    claims,sign=signed_session
    monkeypatch.setattr(database,'connect_postgres',lambda _:pytest.fail('Invalid token reached database'))
    with pytest.raises(HTTPException) as error:
        accounts.authenticated_user('Bearer '+sign(dict(claims,**change)))
    assert error.value.status_code==401


def test_session_database_failure_is_unavailable_not_authenticated(signed_session,monkeypatch):
    claims,sign=signed_session
    def fail(_):raise RuntimeError('secret connection detail')
    monkeypatch.setattr(database,'connect_postgres',fail)
    with pytest.raises(HTTPException) as error:accounts.authenticated_user('Bearer '+sign(claims))
    assert error.value.status_code==503 and 'secret' not in error.value.detail
    monkeypatch.delenv('ACCOUNT_DATABASE_URL')
    with pytest.raises(HTTPException) as error:accounts.authenticated_user('Bearer '+sign(claims))
    assert error.value.status_code==503
