"""Resume two rotating, bounded archive tasks and preserve each outcome."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
TASKS=(
    ('paul_fosh', ['historical_corpus.py','harvest-paul-fosh','--workers','2']),
    ('clive_emson', ['scripts/harvest_clive_emson_canonical.py','--enrich-next','--workers','2']),
    ('edward_mellor', ['scripts/harvest_edward_mellor_results.py','--limit','4','--workers','2']),
    ('sutton_kersh', ['scripts/harvest_sutton_kersh_results.py','--catalogues','4','--workers','2']),
    ('acuitus', ['scripts/harvest_acuitus_canonical.py','--all-incomplete']),
    ('allsop', ['historical_allsop.py','--workers','2']),
)


def execute(command, root, timeout):
    process=subprocess.Popen([sys.executable,*command],cwd=root,start_new_session=True)
    try:
        return 'completed' if process.wait(timeout=timeout)==0 else 'failed'
    except subprocess.TimeoutExpired:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);process.wait()
        return 'timed_out'


def run(root=ROOT,runner=execute,count=2,timeout=600):
    root=Path(root);path=root/'data/auction_history/continuation_collection.json'
    state=json.loads(path.read_text()) if path.exists() else {'next_task':0,'runs':[]}
    for _ in range(min(count,len(TASKS))):
        index=state['next_task']%len(TASKS);name,command=TASKS[index]
        outcome=runner(command,root,timeout)
        state['runs'].append({'source':name,'outcome':outcome,'checked_at':datetime.now(timezone.utc).isoformat()})
        state['runs']=state['runs'][-60:];state['next_task']=(index+1)%len(TASKS)
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(path)
        print(json.dumps(state['runs'][-1]),flush=True)
    return state


if __name__=='__main__':run()
