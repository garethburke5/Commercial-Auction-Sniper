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
