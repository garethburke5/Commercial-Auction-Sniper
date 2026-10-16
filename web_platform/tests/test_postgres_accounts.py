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
        db.execute("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; END $$")
        with db.transaction():db.execute((Path(__file__).parents[1]/'private_schema.sql').read_text())
        db.execute("ALTER ROLE auction_api LOGIN PASSWORD 'disposable_ci_only'")
        names=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='auction_private' AND tablename!='schema_version'").fetchall()
        from psycopg import sql
        db.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(sql.Identifier('auction_private',r[0]) for r in names)))
    dsn=url.replace(parsed.username+':'+parsed.password+'@','auction_api:disposable_ci_only@')
    return Accounts(database_url=dsn)


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
    import subprocess,shutil
    from web_platform.tests.test_report_credits import fund
    a=pg_accounts;a.ensure('alice');fund(a)
    with a.db() as db:
        db.execute('INSERT INTO reviews VALUES (?,?,?,?,?)',('recover-report','alice','p','{"analysis_state":"complete"}',1))
        period=db.execute('SELECT period_start FROM report_credit_periods').fetchone()[0]
        db.execute('INSERT INTO report_credit_redemptions VALUES (?,?,?,?,?)',('recover-report','alice','sub',period,2))
    executable=shutil.which('pg_dump');container=os.getenv('TEST_PG_CONTAINER')
    if not executable and not container:pytest.fail('pg_dump is required for the isolated recovery drill')
    # CI uses the service image's matching PostgreSQL 17 client, avoiding
    # whichever older pg_dump happens to be installed on the runner.
    command=['docker','exec',container,'pg_dump','-U','postgres','-d','auction_test'] if container else [executable]
    parsed=urlsplit(os.environ['TEST_ACCOUNT_DATABASE_URL'])
    env=dict(os.environ,PGHOST=parsed.hostname,PGPORT=str(parsed.port or 5432),PGUSER=parsed.username,PGPASSWORD=parsed.password,PGDATABASE='auction_test')
    archive=tmp_path/'private-backup.sql'
    with archive.open('wb') as f:
        subprocess.run(command+['--data-only','--schema=auction_private','--exclude-table=auction_private.schema_version','--inserts','--no-owner','--no-privileges'],env=env,stdout=f,check=True)
    import psycopg
    # This fixture only accepts localhost/auction_test. Restore inside a
    # transaction and verify all ledger balances/ownership before rollback.
    with psycopg.connect(os.environ['TEST_ACCOUNT_DATABASE_URL']) as db:
        names=db.execute("SELECT tablename FROM pg_tables WHERE schemaname='auction_private' AND tablename!='schema_version'").fetchall()
        from psycopg import sql
        db.execute(sql.SQL('TRUNCATE {}').format(sql.SQL(',').join(sql.Identifier('auction_private',r[0]) for r in names)))
        # pg_dump adds psql-only restrict guards; all data here is generated
        # in this disposable fixture, and SQL is executed without psql.
        restore='\n'.join(line for line in archive.read_text().splitlines() if not line.startswith('\\'))
        db.execute(restore)
        assert db.execute("SELECT r.user_id,p.status FROM auction_private.report_credit_redemptions r JOIN auction_private.report_credit_periods p USING(subscription_id,period_start) WHERE r.review_id='recover-report'").fetchone()==('alice','paid')
        assert db.execute("SELECT report_json FROM auction_private.reviews WHERE id='recover-report'").fetchone()[0]=='{"analysis_state":"complete"}'
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
