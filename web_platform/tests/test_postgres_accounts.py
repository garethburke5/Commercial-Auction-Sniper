"""Run against the disposable PostgreSQL service in CI, never a customer DB."""
import os
from pathlib import Path
from urllib.parse import urlsplit
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from web_platform.accounts import Accounts
from web_platform.database import begin_write,placeholders
from web_platform.tests.test_platform import site


def test_sql_placeholder_translation_preserves_literal_questions():
    assert placeholders("SELECT '?' AS q, ? AS value, 'it''s ?' AS quoted")=="SELECT '?' AS q, %s AS value, 'it''s ?' AS quoted"


@pytest.fixture
def pg_accounts():
    url=os.getenv('TEST_ACCOUNT_DATABASE_URL')
    if not url:pytest.skip('Disposable PostgreSQL integration service not configured')
    parsed=urlsplit(url)
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.path!='/auction_test':
        pytest.fail('Integration tests require the disposable local auction_test database')
    import psycopg
    with psycopg.connect(url,autocommit=True) as db:
        db.execute('CREATE SCHEMA IF NOT EXISTS auth')
        db.execute('CREATE TABLE IF NOT EXISTS auth.users(id uuid PRIMARY KEY,email text,email_confirmed_at timestamptz,is_anonymous boolean,deleted_at timestamptz,banned_until timestamptz)')
        db.execute('CREATE TABLE IF NOT EXISTS auth.sessions(id uuid PRIMARY KEY,user_id uuid NOT NULL,not_after timestamptz)')
        db.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$")
        with db.transaction():db.execute((Path(__file__).parents[1]/'private_schema.sql').read_text())
        with db.transaction():db.execute((Path(__file__).parents[1]/'alert_recipients.sql').read_text())
        with db.transaction():db.execute((Path(__file__).parents[1]/'account_sessions.sql').read_text())
        db.execute('TRUNCATE auth.users,auth.sessions')
        db.execute("ALTER ROLE auction_api LOGIN PASSWORD 'disposable_ci_only'")
        names=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='auction_private' AND tablename!='schema_version'").fetchall()
        from psycopg import sql
        db.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(sql.Identifier('auction_private',r[0]) for r in names)))
    dsn=url.replace(parsed.username+':'+parsed.password+'@','auction_api:disposable_ci_only@')
    return Accounts(database_url=dsn)


def test_postgres_revoked_sessions_fail_before_private_account_access(pg_accounts,site,monkeypatch):
    import hashlib,jwt,psycopg
    from uuid import uuid4
    from types import SimpleNamespace
    from cryptography.hazmat.primitives.asymmetric import rsa
    from web_platform import app as module,accounts as identity
    a=pg_accounts;subject=str(uuid4());sid=str(uuid4());other=str(uuid4())
    issuer='https://session-test.example/auth/v1'
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    claims={'sub':subject,'session_id':sid,'iss':issuer,'aud':'authenticated',
            'iat':int(time.time()),'exp':int(time.time())+300}
    token=jwt.encode(claims,key,algorithm='RS256')
    headers={'Authorization':'Bearer '+token}
    monkeypatch.setenv('AUTH_ISSUER',issuer)
    monkeypatch.setenv('ACCOUNT_DATABASE_URL',a.database_url)
    monkeypatch.setattr(identity,'key_client',lambda _:SimpleNamespace(
        get_signing_key_from_jwt=lambda _:SimpleNamespace(key=key.public_key())))
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    admin_url=os.environ['TEST_ACCOUNT_DATABASE_URL']
    with psycopg.connect(admin_url) as db:
        db.execute('INSERT INTO auth.users VALUES (%s,%s,now(),false,NULL,NULL)',(subject,'session@example.test'))
        db.execute('INSERT INTO auth.sessions VALUES (%s,%s,NULL)',(sid,subject))
        # A repeated base install must not grant writes on either Auth view.
        db.execute((Path(__file__).parents[1]/'private_schema.sql').read_text())
        for role in ('anon','authenticated'):
            assert not db.execute("SELECT has_table_privilege(%s,'auction_private.active_account_sessions','SELECT')",(role,)).fetchone()[0]
        for table in ('auth.sessions','auth.users'):
            assert not db.execute('SELECT has_table_privilege(%s,%s,%s)',('auction_api',table,'SELECT')).fetchone()[0]
        for privilege in ('INSERT','UPDATE','DELETE'):
            assert not db.execute("SELECT has_table_privilege('auction_api','auction_private.active_account_sessions',%s)",(privilege,)).fetchone()[0]
    with TestClient(module.create_app(site)) as client:
        assert client.get('/api/account/identity',headers=headers).status_code==200
        pid=site.catalogue.properties[0]['id']
        assert client.put('/api/account/saved/'+pid,headers=headers).status_code==200
        for update in ["UPDATE auth.users SET banned_until=now()+interval '1 hour'",
                       "UPDATE auth.users SET banned_until=NULL,deleted_at=now()",
                       "UPDATE auth.users SET deleted_at=NULL,is_anonymous=true",
                       "UPDATE auth.users SET is_anonymous=false,email_confirmed_at=NULL",
                       "UPDATE auth.users SET email_confirmed_at=now(); UPDATE auth.sessions SET not_after=now()-interval '1 second'",
                       "UPDATE auth.sessions SET not_after=NULL,user_id='"+other+"'",
                       "DELETE FROM auth.sessions"]:
            with psycopg.connect(admin_url) as db:db.execute(update)
            assert client.get('/api/account/identity',headers=headers).status_code==401
            assert client.get('/api/account',headers=headers).status_code==401
            assert client.get('/api/account/reviews/unknown/download',headers=headers).status_code==401
        # A new session grants the same owner access without restoring the old JWT.
        new_sid=str(uuid4())
        with psycopg.connect(admin_url) as db:db.execute('INSERT INTO auth.sessions VALUES (%s,%s,NULL)',(new_sid,subject))
        fresh={'Authorization':'Bearer '+jwt.encode(dict(claims,session_id=new_sid),key,algorithm='RS256')}
        returned=client.get('/api/account',headers=fresh)
        assert returned.status_code==200 and returned.json()['saved_properties']==[pid]
        assert client.get('/api/account',headers=headers).status_code==401
    assert identity.authenticated_user(fresh['Authorization'])==hashlib.sha256((issuer+'|'+subject).encode()).hexdigest()


def test_postgres_daily_digest_claim_and_recipient_view(pg_accounts,monkeypatch):
    from web_platform.tests.test_alert_delivery import seed,rows,accepted
    from web_platform import alert_delivery as alerts
    import base64,psycopg
    for k,v in {'ALERT_EMAIL_ENABLED':'true','RESEND_API_KEY':'synthetic',
                'RESEND_WEBHOOK_SECRET':'whsec_'+base64.b64encode(b'synthetic-secret').decode(),
                'ALERT_EMAIL_FROM':'Auction Geek <updates@auctiongeek.co.uk>',
                'ALERT_UNSUBSCRIBE_ORIGIN':'https://api.example.test'}.items():monkeypatch.setenv(k,v)
    a=pg_accounts;seed(a)
    subject='00000000-0000-4000-8000-000000000001'
    with a.db() as db:db.execute('UPDATE alert_preferences SET auth_subject=?',(subject,))
    with psycopg.connect(os.environ['TEST_ACCOUNT_DATABASE_URL']) as db:
        db.execute('INSERT INTO auth.users VALUES (%s,%s,now(),false,NULL,NULL)',(subject,'owned@example.test'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(lambda _:alerts.enqueue(a),range(4)))==1
    assert len(rows(a,'alert_outbox_events'))==4
    calls=[]
    def post(*args,**kw):calls.append(kw);return accepted()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:alerts.dispatch(a,post=post),range(4)))
    assert len(calls)==1 and sum(r['accepted'] for r in results)==1
    with a.db() as db:assert alerts.recipient(db,'paid')=='owned@example.test'
    with psycopg.connect(os.environ['TEST_ACCOUNT_DATABASE_URL']) as db:
        db.execute('UPDATE auth.users SET email=%s',('changed@example.test',))
        assert db.execute("SELECT has_table_privilege('auction_api','auth.users','SELECT')").fetchone()[0] is False
        assert db.execute("SELECT has_table_privilege('anon','auction_private.alert_recipients','SELECT')").fetchone()[0] is False
        assert db.execute("SELECT has_table_privilege('auction_api','auction_private.alert_recipients','UPDATE')").fetchone()[0] is False
    with a.db() as db:assert alerts.recipient(db,'paid') is None


def test_postgres_persistence_upserts_and_rollback(pg_accounts):
    a=pg_accounts;a.ensure('alice');a.ensure('alice');a.ensure('bob')
    with a.db() as db:
        db.execute('INSERT INTO saved VALUES (?,?,?) ON CONFLICT(user_id,property_id) DO NOTHING',('alice','property',1))
        db.execute('INSERT INTO saved VALUES (?,?,?) ON CONFLICT(user_id,property_id) DO NOTHING',('alice','property',2))
    fresh=Accounts(database_url=a.database_url)
    with fresh.db() as db:
        row=db.execute('SELECT * FROM saved WHERE user_id=?',('alice',)).fetchone()
        assert dict(row)=={'user_id':'alice','property_id':'property','created_at':1}
        assert row[0]=='alice'
    with pytest.raises(RuntimeError):
        with a.db() as db:
            db.execute('DELETE FROM saved WHERE user_id=?',('alice',))
            raise RuntimeError('rollback')
    with fresh.db() as db:assert db.execute('SELECT COUNT(*) FROM saved').fetchone()[0]==1


def test_postgres_parallel_processing_claim_is_exactly_once(pg_accounts):
    a=pg_accounts
    with a.db() as db:db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',('r','awaiting_payment',0,1))
    def claim(_):
        with a.db() as db:
            begin_write(db)
            row=db.execute('SELECT * FROM review_processing WHERE review_id=?',('r',)).fetchone()
            if row['status']!='awaiting_payment':return False
            time.sleep(.03)
            db.execute("UPDATE review_processing SET status='processing',attempts=attempts+1 WHERE review_id=?",('r',))
            return True
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(claim,range(4)))==1
    with a.db() as db:assert db.execute('SELECT attempts FROM review_processing').fetchone()[0]==1


def test_postgres_interrupted_report_recovery_is_exactly_once(pg_accounts,monkeypatch):
    from web_platform.report_jobs import recover,current
    a=pg_accounts;monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    with a.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('recover','alice','p','{"analysis_state":"awaiting_payment"}',1))
        db.execute('INSERT INTO review_processing VALUES (?,?,?,?)',('recover','processing',1,1))
        db.execute('INSERT INTO report_generation_attempts(review_id,attempt,user_id,started_at,status,upload_bytes,upload_files) VALUES (?,?,?,?,?,?,?)',('recover',1,'alice',1,'processing',4,1))
    def attempt(_):
        try:recover(a,'recover',1,'owner',worker_stopped=True);return True
        except HTTPException as error:
            assert error.status_code==409;return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(attempt,range(4)))==1
    with a.db() as db:
        assert not current(db,'recover',1)
        assert db.execute("SELECT status FROM report_generation_attempts WHERE review_id='recover'").fetchone()[0]=='interrupted'
        assert db.execute('SELECT count(*) FROM report_credit_redemptions').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM purchases').fetchone()[0]==0


def test_postgres_owner_preview_and_customer_isolation(pg_accounts,site,monkeypatch):
    from web_platform import app as module
    a=pg_accounts
    monkeypatch.setattr(module,'authenticated_user',lambda h:h or (_ for _ in ()).throw(HTTPException(401)))
    monkeypatch.setattr(module,'private_services',lambda:(a,None))
    monkeypatch.setenv('ADMIN_ACCOUNT_IDS','owner')
    monkeypatch.setenv('PRIVATE_API_ONLY','true')
    with TestClient(module.create_app(site)) as c:
        pid=site.catalogue.properties[0]['id']
        assert c.put('/api/account/saved/'+pid,headers={'Authorization':'owner'}).status_code==200
        assert c.get('/api/account',headers={'Authorization':'owner'}).json()['saved_properties']==[pid]
        assert c.get('/api/account',headers={'Authorization':'other'}).json()['saved_properties']==[]
        assert c.get('/api/admin/preview/professional',headers={'Authorization':'other'}).status_code==403
        assert c.get('/api/admin/preview/professional',headers={'Authorization':'owner'}).json()['read_only']
        assert a.plan('owner')=='free'
        assert c.put('/api/account/workspace/'+pid,json={'watched':True},headers={'Authorization':'owner'}).status_code==403


def test_postgres_backend_has_no_public_identity_or_ddl_access(pg_accounts):
    import psycopg
    with pg_accounts.db() as db:
        result=db.execute("SELECT has_schema_privilege(current_user,'auth','USAGE') AS can_read_auth,has_schema_privilege(current_user,'auction_private','CREATE') AS can_create").fetchone()
        assert not result['can_read_auth'] and not result['can_create']
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with pg_accounts.db() as db:db.execute('UPDATE schema_version SET version=99')


def test_postgres_credit_race_and_persistent_report_ownership(pg_accounts,monkeypatch):
    from web_platform.tests.test_report_credits import fund
    from web_platform.report_credits import redeem,balance
    from web_platform.workspace import full_review_allowed
    a=pg_accounts;a.ensure('alice');a.ensure('bob');fund(a)
    with a.db() as db:
        for n in range(4):db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('r'+str(n),'alice','p','{}',1))
    monkeypatch.setattr('acquisition_quality.paid_report_status',lambda:{'purchase_available':True})
    def claim(n):
        try:redeem(a,'alice','r'+str(n));return 1
        except HTTPException as e:assert e.status_code==402;return 0
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(claim,range(4)))==1
    fresh=Accounts(database_url=a.database_url)
    assert balance(fresh,'alice')['remaining']==0
    with fresh.db() as db:
        rid=db.execute('SELECT review_id FROM report_credit_redemptions').fetchone()[0]
        db.execute("UPDATE subscriptions SET status='canceled'")
    assert full_review_allowed(fresh,'alice',rid,'p')
    assert not full_review_allowed(fresh,'bob',rid,'p')


def test_disposable_postgres_backup_restores_credit_and_report_ownership(pg_accounts,tmp_path):
    """Recovery drill on CI-only data, never against the configured Supabase DB."""
    import subprocess,shutil,hashlib,psycopg
    from web_platform.tests.test_report_credits import fund
    a=pg_accounts;a.ensure('alice');fund(a)
    subject='00000000-0000-4000-8000-000000000002'
    issuer='https://recovery-fixture.example/auth/v1'
    uid=hashlib.sha256((issuer+'|'+subject).encode()).hexdigest()
    with psycopg.connect(os.environ['TEST_ACCOUNT_DATABASE_URL']) as db:
        db.execute('INSERT INTO auth.users VALUES (%s,%s,now(),false,NULL,NULL)',(subject,'recovery@example.test'))
    with a.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('recover-report','alice','p','{"analysis_state":"complete"}',1))
        period=db.execute('SELECT period_start FROM report_credit_periods').fetchone()[0]
        db.execute('INSERT INTO report_credit_redemptions VALUES (?,?,?,?,?)',('recover-report','alice','sub',period,2))
        for table in ('accounts','subscriptions','report_credit_periods','report_credit_redemptions','reviews'):
            db.execute('UPDATE '+table+' SET user_id=? WHERE user_id=?',(uid,'alice'))
        # Restore must preserve opt-out and an unknown provider outcome: neither
        # should become a fresh email or a new paid report/credit after recovery.
        db.execute('INSERT INTO alert_preferences VALUES (?,?,?,?,?,?,?)',
                   (uid,subject,'recovery@example.test',0,1,'fixture-unsubscribe',1))
        db.execute("INSERT INTO alert_outbox(id,user_id,payload_json,status,created_at,next_attempt_at,lease_until,attempts,last_error) VALUES (?,?,?,'needs_review',1,1,0,1,'provider_outcome_unknown')",
                   ('recover-digest',uid,'{}'))
    executable=shutil.which('pg_dump');container=os.getenv('TEST_PG_CONTAINER')
    if not executable and not container:pytest.fail('pg_dump is required for the isolated recovery drill')
    # CI uses the service image's matching PostgreSQL 17 client, avoiding
    # whichever older pg_dump happens to be installed on the runner.
    command=['docker','exec',container,'pg_dump','-U','postgres','-d','auction_test'] if container else [executable]
    parsed=urlsplit(os.environ['TEST_ACCOUNT_DATABASE_URL'])
    env=dict(os.environ,PGHOST=parsed.hostname,PGPORT=str(parsed.port or 5432),PGUSER=parsed.username,PGPASSWORD=parsed.password,PGDATABASE='auction_test')
    archive=tmp_path/'private-backup.sql'
    with archive.open('wb') as f:
        subprocess.run(command+['--data-only','--schema=auction_private','--schema=auth','--exclude-table=auction_private.schema_version','--inserts','--no-owner','--no-privileges'],env=env,stdout=f,check=True)
    # This fixture only accepts localhost/auction_test. Restore inside a
    # transaction and verify all ledger balances/ownership before rollback.
    with psycopg.connect(os.environ['TEST_ACCOUNT_DATABASE_URL']) as db:
        names=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='auction_private' AND tablename!='schema_version'").fetchall()
        from psycopg import sql
        db.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(sql.Identifier('auction_private',r[0]) for r in names)))
        db.execute('TRUNCATE auth.users')
        # pg_dump adds psql-only restrict guards; all data here is generated
        # in this disposable fixture, and SQL is executed without psql.
        restore='\n'.join(line for line in archive.read_text().splitlines() if not line.startswith('\\'))
        db.execute(restore)
        assert db.execute("SELECT r.user_id,p.status FROM auction_private.report_credit_redemptions r JOIN auction_private.report_credit_periods p USING(subscription_id,period_start) WHERE r.review_id='recover-report'").fetchone()==(uid,'paid')
        assert db.execute("SELECT report_json FROM auction_private.reviews WHERE id='recover-report'").fetchone()[0]=='{"analysis_state":"complete"}'
        restored_subject=str(db.execute("SELECT id FROM auth.users WHERE email='recovery@example.test'").fetchone()[0])
        assert hashlib.sha256((issuer+'|'+restored_subject).encode()).hexdigest()==uid
        assert db.execute('SELECT enabled FROM auction_private.alert_preferences WHERE user_id=%s',(uid,)).fetchone()[0]==0
        assert db.execute("SELECT status FROM auction_private.alert_outbox WHERE id='recover-digest'").fetchone()[0]=='needs_review'
        assert db.execute('SELECT count(*) FROM auction_private.alert_recipients').fetchone()[0]==0
        db.rollback()


def test_postgres_watch_transition_claims_and_recurring_changes(pg_accounts):
    from web_platform.tests.test_scheduled_monitoring import exercise_watch_transitions
    exercise_watch_transitions(pg_accounts)


def test_postgres_saved_search_concurrency_and_isolation(pg_accounts):
    from web_platform.tests.test_search_monitoring import exercise_matches
    exercise_matches(pg_accounts)


def test_postgres_monitoring_job_claim_and_recovery(pg_accounts,site):
    from web_platform.tests.test_monitoring_activation import exercise_job
    exercise_job(pg_accounts,site)
