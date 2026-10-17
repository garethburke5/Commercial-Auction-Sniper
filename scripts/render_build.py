"""Prepare the disposable Render checkout before its build is packaged.

The repository retains all captured evidence. Only Render's temporary clone is
trimmed: Git's object database and raw collector source captures are not read by
the private API. Keep canonical snapshots, history databases and observations.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

RENDER_CHECKOUT = Path('/opt/render/project/src')
BUILD_ONLY_PATHS = ('.git', 'data/auction_history/sources')
REQUIRED_FILES = (
    'web_platform/requirements.txt', 'web_platform/app.py',
    'data/properties.json', 'data/property_history.json',
    'data/auction_history/progress.json',
    'data/auction_history/auction_history.sqlite.gz',
)


def prepare_checkout(root, environ):
    root = Path(root)
    if environ.get('RENDER') != 'true' or root != RENDER_CHECKOUT or root.resolve() != root:
        raise RuntimeError('Build cleanup is restricted to the disposable Render checkout')
    for name in REQUIRED_FILES:
        path = root / name
        if not path.is_file() or path.resolve() != path:
            raise RuntimeError(f'Required runtime file is missing or linked: {name}')
    # Validate the entire removal list before touching anything. Never follow a
    # symlink to a shared checkout, mounted corpus or customer storage directory.
    targets = []
    for name in BUILD_ONLY_PATHS:
        path = root / name
        if path.is_symlink() or path.resolve() != path:
            raise RuntimeError(f'Refusing linked build-only path: {name}')
        if path.exists():
            if not path.is_dir():
                raise RuntimeError(f'Expected a disposable directory: {name}')
            targets.append((name, path))
    for name, path in targets:
        shutil.rmtree(path)
        print(f'Removed build-only checkout copy: {name}', flush=True)
    print('Canonical property/history files retained', flush=True)


def main():
    root = Path(__file__).resolve().parents[1]
    prepare_checkout(root, os.environ)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-cache-dir',
                    '-r', 'web_platform/requirements.txt'], cwd=root, check=True)


if __name__ == '__main__':
    main()
