from datetime import datetime, timezone
import pytest
from web_platform.accounts import Accounts
from web_platform.workspace import update, dashboard
from web_platform.monitoring import refresh
from web_platform.tests.test_membership_product import subscribe


def test_batch_monitors_paid_accounts_once_and_preserves_outage_baselines(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite')
    subscribe(a, 'active'); subscribe(a, 'expired')
    row={'id':'p','address':'Synthetic property','path':'/property/p/','source':'Example','guide_price':100000}
    for user in ('active','expired'):
        update(a,user,'p',{'watched':True},row)
    with a.db() as db:db.execute("UPDATE subscriptions SET valid_until=1 WHERE user_id='expired'")
    snapshot={'generated_at':datetime.now(timezone.utc).isoformat(),'properties':[row],
              'source_health':[{'source':'Example','status':'DEGRADED'}]}
    changed=dict(row,guide_price=90000)
    assert refresh(a,{'p':changed},snapshot)['events_added']==0
    snapshot['source_health'][0]['status']='LIVE'
    assert refresh(a,{'p':changed},snapshot)['events_added']==1
    assert refresh(a,{'p':changed},snapshot)['events_added']==0
    assert len(dashboard(a,'active',{'p':changed})['events'])==1
    assert not dashboard(a,'expired',{'p':changed})['events']
    assert refresh(a,{},snapshot)['events_added']==0


def test_stale_snapshot_cannot_generate_customer_monitoring_events(tmp_path):
    a=Accounts(tmp_path/'accounts.sqlite')
    with pytest.raises(ValueError,match='older than'):
        refresh(a,{}, {'generated_at':'2020-01-01T00:00:00Z','properties':[{}]})
