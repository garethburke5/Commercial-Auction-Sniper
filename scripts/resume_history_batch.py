"""Resume rotating, bounded archive tasks and preserve each outcome."""
from datetime import datetime,timezone
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TASKS=(
    ('paul_fosh', ['historical_corpus.py','harvest-paul-fosh','--workers','2']),
    ('clive_emson', ['scripts/harvest_clive_emson_canonical.py','--enrich-next','--workers','2']),
    ('edward_mellor', ['scripts/harvest_edward_mellor_results.py','--limit','4','--workers','2']),
    ('sutton_kersh', ['scripts/harvest_sutton_kersh_results.py','--catalogues','4','--workers','2']),
    ('acuitus', ['scripts/harvest_acuitus_canonical.py','--all-incomplete']),
    ('allsop', ['historical_allsop.py','--workers','2']),
    ('savills', ['historical_corpus.py','harvest-savills','--workers','2']),
    ('clive_emson_catalogues', ['scripts/harvest_clive_emson_canonical.py','--all-incomplete']),
    ('mchugh', ['scripts/harvest_mchugh_results.py','2']),
    ('phillip_arnold', ['scripts/harvest_phillip_arnold_results.py','2']),
    ('harman_healy_results', ['scripts/harvest_harman_healy_results.py']),
    # Serial browser-session/read-through recovery for a legacy filter route.
    ('agents_property_auction', ['scripts/harvest_agents_property_auction_results.py','2','--workers','1']),
    ('lsh_results', ['scripts/harvest_lsh_results.py']),
    ('goldings_results', ['scripts/harvest_goldings_results.py']),
    ('maggs_allen_results', ['scripts/harvest_maggs_allen_results.py']),
    ('knight_frank_results', ['scripts/harvest_knight_frank_results.py', '12']),
    ('auction_estates_results', ['scripts/harvest_auction_estates_results.py', '8']),
    ('hollis_morgan_results', ['scripts/harvest_hollis_morgan_results.py', '4']),
    ('dedman_gray_results', ['scripts/harvest_dedman_gray_results.py', '--workers', '2']),
    ('john_francis_results', ['scripts/harvest_john_francis_results.py', '--workers', '2']),
    ('swift_property_auctions', ['scripts/harvest_swift_property_auctions.py', '--workers', '2']),
    ('sharpes_results', ['scripts/harvest_sharpes_results.py', '--workers', '2']),
    ('seel_catalogues', ['scripts/harvest_seel_catalogues.py']),
    ('bond_wolfe_history', ['scripts/harvest_bond_wolfe_history.py']),
    ('barnett_ross_canonical', ['scripts/harvest_barnett_ross_canonical.py', '--all-incomplete']),
    ('pugh_canonical', ['scripts/harvest_pugh_canonical.py']),
    ('symonds_sampson_canonical', ['scripts/harvest_symonds_sampson_canonical.py', '--workers', '2']),
    ('symonds_sampson_events', ['scripts/harvest_symonds_sampson_events.py', '--workers', '4']),
    ('bidx1_canonical', ['scripts/harvest_bidx1_canonical.py']),
    ('strettons_results', ['scripts/harvest_strettons_results.py', '4']),
    ('cheffins_history', ['scripts/harvest_cheffins_history.py', '6']),
    ('btg_eddisons_catalogues', ['scripts/harvest_btg_eddisons_catalogues.py', '4']),
    ('sdl_legacy_catalogues', ['scripts/harvest_sdl_legacy_catalogues.py', '--limit', '48']),
    ('smith_sons_results', ['scripts/harvest_smith_sons_results.py']),
    ('town_country_results', ['scripts/harvest_town_country_results.py', '--workers', '2']),
    ('brown_co_results', ['scripts/harvest_brown_co_results.py']),
    ('bagshaws_results', ['scripts/harvest_bagshaws_results.py']),
    ('anderson_garland_results', ['scripts/harvest_anderson_garland_results.py']),
    ('edward_mellor_pdfs', ['scripts/harvest_edward_mellor_pdfs.py', '8']),
    ('future_property_auctions', ['scripts/harvest_future_property_auctions.py', '--limit', '18', '--workers', '2']),
    ('auction_house_northeast', ['scripts/harvest_auction_house_northeast.py']),
    ('auction_house_south_yorkshire', ['scripts/harvest_auction_house_south_yorkshire.py']),
    ('auction_house_north_west', ['scripts/harvest_auction_house_north_west.py']),
    ('auction_house_south_west', ['scripts/harvest_auction_house_south_west.py']),
    ('auction_house_east_anglia', ['scripts/harvest_auction_house_east_anglia.py']),
    ('auction_house_national', ['scripts/harvest_auction_house_national.py']),
    ('auction_house_regions', ['scripts/harvest_auction_house_regions.py']),
    ('network_auctions', ['scripts/harvest_network_auctions.py', '6']),
    ('cottons_results', ['scripts/harvest_cottons_results.py', '16', '16']),
    ('cottons_guides', ['scripts/enrich_cottons_guides.py', '2']),
    ('pattinson_history', ['scripts/harvest_pattinson_history.py', '32']),
    ('eddisons_insights', ['scripts/harvest_eddisons_insights.py']),
    ('mchugh_legacy', ['scripts/harvest_mchugh_legacy.py', '8']),
    ('barnard_marcus', ['scripts/resume_barnard_marcus_history.py', '--limit', '4']),
    ('dawsons_results', ['scripts/harvest_dawsons_history.py']),
)

# These rolling archives have explicitly reconciled pagination. Re-fetching
# hundreds of unchanged result pages every rotation consumes the recovery
# budget without extending historical coverage. Still refresh every six hours;
# missing summaries, positive gains, incomplete runs and failures never defer.
RECONCILED_REFRESHES = {
    'auction_house_northeast': 'auction_house_northeast_collection.json',
    'auction_house_south_yorkshire': 'auction_house_southyorkshire_collection.json',
    'auction_house_north_west': 'auction_house_northwest_collection.json',
    'auction_house_south_west': 'auction_house_southwest_collection.json',
    'auction_house_east_anglia': 'auction_house_eastanglia_collection.json',
    'auction_house_national': 'auction_house_national_collection.json',
    'town_country_results': 'town_country_collection.json',
    'pugh_canonical': 'pugh_collection.json',
    'symonds_sampson_events': 'symonds_sampson_event_collection.json',
}


def refresh_deferral(root, name, last, now=None):
    filename = RECONCILED_REFRESHES.get(name)
    if not filename or not last or last.get('outcome') != 'completed':
        return None
    try:
        summary = json.loads((Path(root)/'data/auction_history'/filename).read_text())
        checked = datetime.fromisoformat(summary['checked_at'])
        age = ((now or datetime.now(timezone.utc))-checked).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if (summary.get('archive_pagination_complete') is True
            and summary.get('run_new_appearances') == 0
            and not summary.get('failures') and not summary.get('blocked_pages')
            and not summary.get('detail_recovery_failures') and 0 <= age < 21600):
        return {'outcome':'deferred_unchanged_archive',
                'reason':'explicitly reconciled archive produced no new appearances; six-hour refresh',
                'retry_after_seconds':round(21600-age)}
    return None


def execute(command, root, timeout):
    # Capture a bounded diagnostic tail without buffering an entire harvest in RAM.
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen([sys.executable,'-u',*command],cwd=root,start_new_session=True,
                                 stdout=log,stderr=subprocess.STDOUT)
        try:
            code=process.wait(timeout=timeout)
            outcome='completed' if code==0 else 'failed'
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
            code=process.returncode;outcome='timed_out'
        length=log.tell();log.seek(max(0,length-6000))
        tail=log.read().decode('utf-8','replace')
        return {'outcome':outcome,'exit_code':code,'diagnostic_tail':tail}


def run(root=ROOT,runner=execute,count=2,timeout=600,budget=None,clock=time.monotonic):
    root=Path(root);path=root/'data/auction_history/continuation_collection.json'
    state=json.loads(path.read_text()) if path.exists() else {'next_task':0,'runs':[]}
    started=clock()
    for _ in range(min(count,len(TASKS))):
        remaining=None if budget is None else budget-(clock()-started)
        if remaining is not None and remaining<1:break
        index=state['next_task']%len(TASKS);name,command=TASKS[index]
        task_started=clock()
        deferred=refresh_deferral(root,name,state.get('latest_by_source',{}).get(name))
        outcome=deferred or runner(command,root,timeout if remaining is None else min(timeout,remaining))
        result={'outcome':outcome} if isinstance(outcome,str) else outcome
        entry={'source':name,**result,'duration_seconds':round(clock()-task_started,2),
               'checked_at':datetime.now(timezone.utc).isoformat()}
        state['runs'].append(entry)
        # A skipped check is not a fresh successful capture and must not reset
        # either the evidence timestamp or the six-hour refresh clock.
        if not deferred:
            state.setdefault('latest_by_source',{})[name]=entry
        state['runs']=state['runs'][-500:];state['next_task']=(index+1)%len(TASKS)
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2)+'\n');temp.replace(path)
        print(json.dumps(state['runs'][-1]),flush=True)
    return state


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=len(TASKS))
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--budget',type=int,default=1200)
    args=parser.parse_args()
    run(count=args.count,timeout=args.timeout,budget=args.budget)
