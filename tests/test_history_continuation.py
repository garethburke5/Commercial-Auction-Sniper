from scripts.resume_history_batch import run,TASKS


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
