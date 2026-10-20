"""Resume rotating, bounded archive tasks and preserve each outcome."""
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
    ('savills', ['historical_corpus.py','harvest-savills','--workers','2']),
    ('clive_emson_catalogues', ['scripts/harvest_clive_emson_canonical.py','--all-incomplete']),
    ('mchugh', ['scripts/harvest_mchugh_results.py','2']),
    ('phillip_arnold', ['scripts/harvest_phillip_arnold_results.py','2']),
    ('harman_healy_results', ['scripts/harvest_harman_healy_results.py']),
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
    ('pattinson_history', ['scripts/harvest_pattinson_history.py', '32']),
    ('eddisons_insights', ['scripts/harvest_eddisons_insights.py']),
    ('mchugh_legacy', ['scripts/harvest_mchugh_legacy.py', '8']),
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


if __name__=='__main__':run(count=4,timeout=300)
