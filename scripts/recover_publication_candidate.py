"""Recover fresh main-branch collector facts for the normal publication gate.

Only original GitHub Actions artifacts from the two production collection
workflows are eligible. This never changes collection timestamps and never
publishes by itself: callers must still run revalidation and all quality gates.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from scripts.check_collection_freshness import check

WORKFLOWS = ('auction-sniper-publish-now.yml', 'auction-sniper-scan.yml')
MAX_BYTES = 64 * 1024 * 1024


def eligible(candidate, current):
    if check(candidate):
        return False
    if any(k not in candidate for k in ('archive', 'source_health', 'integrity')):
        return False
    from datetime import datetime
    try:
        new = datetime.fromisoformat(candidate['generated_at'].replace('Z','+00:00'))
        old = datetime.fromisoformat(str(current.get('generated_at')).replace('Z','+00:00'))
        return new > old
    except (ValueError, TypeError):
        return False


def api(path):
    return subprocess.check_output(['gh', 'api', path])


def recover(path=Path('data/properties.json'), repository=None):
    repository=repository or os.environ['GITHUB_REPOSITORY']
    path=Path(path);current=json.loads(path.read_text())
    runs=[]
    for workflow in WORKFLOWS:
        result=json.loads(api(f'repos/{repository}/actions/workflows/{workflow}/runs?branch=main&per_page=10'))
        runs.extend(r for r in result['workflow_runs'] if r.get('head_branch')=='main' and (r.get('head_repository') or {}).get('full_name')==repository)
    for run in sorted(runs,key=lambda r:r['created_at'],reverse=True):
        # Facts collected by a fork or an unrelated code lineage are ineligible.
        if subprocess.run(['git','merge-base','--is-ancestor',run['head_sha'],'HEAD'],capture_output=True).returncode:
            continue
        artifacts=json.loads(api(f"repos/{repository}/actions/runs/{run['id']}/artifacts"))['artifacts']
        artifact=next((a for a in artifacts if a['name']=='candidate-unpublished-snapshot' and not a['expired'] and a['size_in_bytes']<=MAX_BYTES),None)
        if artifact is None:
            continue
        archive=api(f"repos/{repository}/actions/artifacts/{artifact['id']}/zip")
        if len(archive)>MAX_BYTES:
            raise ValueError('Candidate archive exceeds the size limit')
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            matches=[i for i in z.infolist() if i.filename=='properties.json']
            if len(matches)!=1 or matches[0].file_size>MAX_BYTES:
                raise ValueError('Invalid candidate snapshot archive')
            candidate=json.loads(z.read(matches[0]))
        # Match the snapshot's collector audit fields to the artifact producer.
        integrity=candidate.get('integrity') or {}
        if (str(integrity.get('publication_run_id')) != str(run['id'])
                or integrity.get('collector_revision') != run['head_sha']):
            continue
        if eligible(candidate,current):
            path.write_text(json.dumps(candidate,indent=2),encoding='utf-8')
            print('RECOVERED CANDIDATE',run['id'],candidate['generated_at'],'for normal quality validation')
            return run['id']
        # Continue past an older finished run if another workflow has newer data.
    print('No newer fresh production candidate found; keeping the published snapshot')
    return None


if __name__=='__main__':
    recover()
