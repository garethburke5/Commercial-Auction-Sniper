import gzip
import io
import json
import pytest
from web_platform.history_storage import publish_parts,unpack


def test_split_archive_is_identical_and_preferred_over_stale_legacy(tmp_path):
    raw=bytes(range(256))*100
    packed=tmp_path/'auction_history.sqlite.gz';packed.write_bytes(gzip.compress(raw))
    manifest=publish_parts(packed,tmp_path/'database_parts',part_bytes=60)
    assert len(manifest['parts'])>1
    packed.write_bytes(gzip.compress(b'outdated'))
    output=io.BytesIO();unpack(tmp_path,output)
    assert output.getvalue()==raw
    before=set(p.name for p in (tmp_path/'database_parts').iterdir())
    packed.write_bytes(gzip.compress(raw))
    publish_parts(packed,tmp_path/'database_parts',part_bytes=60)
    assert before==set(p.name for p in (tmp_path/'database_parts').iterdir())


@pytest.mark.parametrize('damage',['missing','corrupt','path'])
def test_corrupt_parts_never_fall_back_to_old_database(tmp_path,damage):
    packed=tmp_path/'auction_history.sqlite.gz';packed.write_bytes(gzip.compress(b'x'*2000))
    parts=tmp_path/'database_parts';manifest=publish_parts(packed,parts,part_bytes=20)
    path=parts/manifest['parts'][0]['name']
    if damage=='missing':path.unlink()
    elif damage=='corrupt':path.write_bytes(b'x'*path.stat().st_size)
    else:
        manifest['parts'][0]['name']='../auction_history.sqlite.gz'
        (parts/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises((ValueError,FileNotFoundError,gzip.BadGzipFile)):
        unpack(tmp_path,io.BytesIO())


def test_legacy_archive_remains_readable(tmp_path):
    (tmp_path/'auction_history.sqlite.gz').write_bytes(gzip.compress(b'legacy'))
    output=io.BytesIO();unpack(tmp_path,output)
    assert output.getvalue()==b'legacy'
