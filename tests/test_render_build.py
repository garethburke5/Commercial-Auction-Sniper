from pathlib import Path

import pytest

from scripts import render_build


def fixture_checkout(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    root.mkdir()
    monkeypatch.setattr(render_build, 'RENDER_CHECKOUT', root)
    for name in render_build.REQUIRED_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'runtime sentinel')
    for name in render_build.BUILD_ONLY_PATHS:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        (path / 'capture').write_bytes(b'disposable clone')
    return root


def test_prunes_only_build_copies_and_retains_runtime_data(tmp_path, monkeypatch):
    root = fixture_checkout(tmp_path, monkeypatch)
    extra = root / 'data/customer-file'
    extra.write_bytes(b'untouched')
    render_build.prepare_checkout(root, {'RENDER': 'true'})
    render_build.prepare_checkout(root, {'RENDER': 'true'})
    assert all(not (root / name).exists() for name in render_build.BUILD_ONLY_PATHS)
    assert all((root / name).read_bytes() == b'runtime sentinel' for name in render_build.REQUIRED_FILES)
    assert extra.read_bytes() == b'untouched'


@pytest.mark.parametrize('env', [{}, {'RENDER': 'false'}])
def test_refuses_non_render_environment_before_removal(tmp_path, monkeypatch, env):
    root = fixture_checkout(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match='restricted'):
        render_build.prepare_checkout(root, env)
    assert (root / '.git/capture').exists()


def test_refuses_wrong_checkout_even_with_render_flag(tmp_path):
    with pytest.raises(RuntimeError, match='restricted'):
        render_build.prepare_checkout(tmp_path, {'RENDER': 'true'})


def test_missing_runtime_history_prevents_all_removal(tmp_path, monkeypatch):
    root = fixture_checkout(tmp_path, monkeypatch)
    (root / 'data/auction_history/auction_history.sqlite.gz').unlink()
    with pytest.raises(RuntimeError, match='Required runtime file'):
        render_build.prepare_checkout(root, {'RENDER': 'true'})
    assert (root / '.git/capture').exists()


def test_symlink_capture_is_not_followed_or_partially_pruned(tmp_path, monkeypatch):
    root = fixture_checkout(tmp_path, monkeypatch)
    capture = root / 'data/auction_history/sources'
    capture.rename(root / 'retained')
    capture.symlink_to(root / 'retained', target_is_directory=True)
    with pytest.raises(RuntimeError, match='linked build-only'):
        render_build.prepare_checkout(root, {'RENDER': 'true'})
    assert (root / '.git/capture').exists()
    assert (root / 'retained/capture').exists()
