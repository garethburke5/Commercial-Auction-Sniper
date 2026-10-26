import json
from pathlib import Path

from scripts.resume_history_batch import run,TASKS


def test_banked_continuation_checkpoint_is_valid_json():
    path = Path(__file__).resolve().parents[1] / "data/auction_history/continuation_collection.json"
    state = json.loads(path.read_text())
    assert isinstance(state.get("runs"), list)
    assert isinstance(state.get("next_task"), int)


def test_only_explicitly_reconciled_zero_growth_archive_is_deferred(tmp_path):
    import json
    from datetime import datetime, timezone, timedelta
    from scripts.resume_history_batch import refresh_deferral
    now = datetime(2026, 10, 25, 20, tzinfo=timezone.utc)
    path = tmp_path/'data/auction_history/auction_house_northeast_collection.json'
    path.parent.mkdir(parents=True)
    summary = {'checked_at':(now-timedelta(hours=1)).isoformat(),
               'archive_pagination_complete':True,'run_new_appearances':0,'failures':[]}
    def check():
        path.write_text(json.dumps(summary))
        return refresh_deferral(tmp_path,'auction_house_northeast',{'outcome':'completed'},now)
    assert check()['retry_after_seconds'] == 18000
    summary['run_new_appearances'] = 5
    assert check() is None
    summary['run_new_appearances'] = 0
    summary['archive_pagination_complete'] = False
    assert check() is None
    summary['archive_pagination_complete'] = True
    summary['failures'] = ['page 2 unavailable']
    assert check() is None
    summary['failures'] = []
    summary['checked_at'] = (now-timedelta(hours=6)).isoformat()
    assert check() is None
    assert refresh_deferral(tmp_path,'auction_house_northeast',{'outcome':'timed_out'},now) is None


def test_unchanged_agents_latest_table_is_deferred_without_retrying_terminal_filters(tmp_path):
    import json
    from datetime import datetime, timezone, timedelta
    from scripts.resume_history_batch import refresh_deferral
    now = datetime(2026, 10, 26, 7, tzinfo=timezone.utc)
    path = tmp_path/'data/auction_history/agents_property_auction_collection.json'
    path.parent.mkdir(parents=True)
    summary = {
        'checked_at': (now-timedelta(hours=1)).isoformat(),
        'appearances_captured': 35,
        'run_new_appearances': 0,
        'run_failures': [],
        'source_blocker': {'kind': 'filtered_archive_http_500'},
    }
    path.write_text(json.dumps(summary))
    deferred = refresh_deferral(tmp_path, 'agents_property_auction', {'outcome':'completed'}, now)
    assert deferred['retry_after_seconds'] == 18000
    summary['run_new_appearances'] = 1
    path.write_text(json.dumps(summary))
    assert refresh_deferral(tmp_path, 'agents_property_auction', {'outcome':'completed'}, now) is None


def test_skipping_unchanged_archive_preserves_last_capture_and_advances(tmp_path):
    import json
    from datetime import datetime, timezone
    path = tmp_path/'data/auction_history/continuation_collection.json'
    path.parent.mkdir(parents=True)
    checked = datetime.now(timezone.utc).isoformat()
    previous = {'outcome':'completed','checked_at':checked}
    index = next(i for i, (name, _) in enumerate(TASKS) if name == 'auction_house_northeast')
    path.write_text(json.dumps({'next_task':index,'runs':[], 'latest_by_source':{'auction_house_northeast':previous}}))
    (path.parent/'auction_house_northeast_collection.json').write_text(json.dumps({
        'checked_at':checked,'archive_pagination_complete':True,'run_new_appearances':0,'failures':[]}))
    calls=[]
    result=run(tmp_path,lambda *args:calls.append(args) or 'completed',count=2)
    assert len(calls)==1 and result['next_task']==index+2
    assert result['latest_by_source']['auction_house_northeast']==previous
    assert result['runs'][0]['outcome']=='deferred_unchanged_archive'


def test_timeout_advances_rotation_without_claiming_capture(tmp_path):
    commands=[]
    def runner(command,root,timeout):
        commands.append(command);return 'timed_out' if len(commands)==1 else 'completed'
    first=run(tmp_path,runner)
    assert first['next_task']==2
    assert [r['outcome'] for r in first['runs']]==['timed_out','completed']
    second=run(tmp_path,runner)
    assert commands[2]==TASKS[2][1] and second['next_task']==4
    assert all('captured' not in r for r in second['runs'])


def test_expanded_batch_wraps_and_preserves_existing_cursor(tmp_path):
    import json
    from pathlib import Path
    path=tmp_path/'data/auction_history/continuation_collection.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'next_task':len(TASKS)-2,'runs':[]}))
    observed=[]
    def runner(command,root,timeout):
        observed.append((command,timeout));return 'completed'
    result=run(tmp_path,runner,count=4,timeout=300)
    assert [c for c,t in observed]==[TASKS[-2][1],TASKS[-1][1],TASKS[0][1],TASKS[1][1]]
    assert result['next_task']==2
    assert all(t==300 for c,t in observed)
    assert len({name for name,command in TASKS})==len(TASKS)
    project=Path(__file__).resolve().parents[1]
    assert all((project/command[0]).is_file() for name,command in TASKS)

def test_fast_tasks_use_remaining_budget_and_keep_source_failures(tmp_path):
    elapsed=[0]
    def runner(command,root,timeout):
        elapsed[0]+=1
        return {'outcome':'failed','exit_code':1,'diagnostic_tail':'archive no longer exposes lot cards'}
    result=run(tmp_path,runner,count=len(TASKS),timeout=300,budget=8,clock=lambda:elapsed[0])
    assert len(result['runs'])==8 and result['next_task']==8
    assert len(result['latest_by_source'])==8
    assert result['runs'][0]['diagnostic_tail']=='archive no longer exposes lot cards'

def test_task_timeout_is_capped_to_remaining_batch_budget(tmp_path):
    seen=[]
    def runner(command,root,timeout):seen.append(timeout);return 'completed'
    run(tmp_path,runner,count=1,timeout=300,budget=12,clock=lambda:0)
    assert seen==[12]


def test_agents_property_auction_result_rows_keep_month_only_and_undisclosed_null():
    from scripts.harvest_agents_property_auction_results import parse_result_page
    html='''
      <h1>Results from our auction at Newcastle in February 2012</h1>
      <table class="table--results"><tbody>
        <tr><td>1 High Street, Durham, DH1 1AA</td><td>£55,000</td></tr>
        <tr><td>Land at 1 High Street, Durham, DH1 1AA</td><td>undisclosed</td></tr>
      </tbody></table>
    '''
    state,rows=parse_result_page(html,'https://example.test/results','Newcastle',2012,2,{'sha256':'abc'})
    assert state['catalogue_complete'] is False
    assert state['result_rows_complete'] is True
    assert state['published_auction_month']=='2012-02'
    assert [row['auction_date'] for row in rows]==[None,None]
    assert [row['sale_price'] for row in rows]==[55000,None]
    assert all(row['record_quality']=='address_record' for row in rows)
    assert rows[0]['property_id'] != rows[1]['property_id']


def test_agents_property_auction_rejects_filter_fallback():
    import pytest
    from scripts.harvest_agents_property_auction_results import parse_result_page
    html='<h1>Results from our latest auction at Cumbria in March 2026</h1>'
    with pytest.raises(ValueError,match='not Newcastle February 2012'):
        parse_result_page(html,'https://example.test/results','Newcastle',2012,2,{})


def test_agents_property_auction_reader_markdown_is_admitted_with_original_url():
    from scripts.harvest_agents_property_auction_results import parse_result_page
    markdown='''
    # Auction Results
    Results from our auction at Newcastle in February 2012
    Address | Sold Price
    --- | ---
    28a Norbury Grove, Walker, Newcastle upon Tyne | £35,000
    5 Grievestead Farm Cottages, Berwick upon Tweed | undisclosed
    #### Navigation
    '''
    url='https://www.agentspropertyauction.com/auctions/auction-results/?a_month=02&a_sub=1&a_venue=Newcastle&a_year=2012'
    state,rows=parse_result_page(markdown,url,'Newcastle',2012,2,{
        'document_format':'markdown','retrieval_url':'https://r.jina.ai/http://example.test'
    })
    assert len(rows)==2 and rows[0]['sale_price']==35000 and rows[1]['sale_price'] is None
    assert all(row['original_url']==url for row in rows)
    assert state['catalogue_complete'] is False
