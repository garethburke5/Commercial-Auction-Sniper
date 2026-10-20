"""Stream a verified history database beyond GitHub's single-file limit."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil

PART_BYTES = 32 * 1024 * 1024


def publish_parts(packed, destination, *, part_bytes=PART_BYTES):
    packed, destination = Path(packed), Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    parts=[]
    with packed.open('rb') as source:
        while data := source.read(part_bytes):
            digest=hashlib.sha256(data).hexdigest()
            name=f'{len(parts):04d}-{digest}.gzpart'
            path=destination/name
            if not path.exists():
                temp=path.with_suffix('.tmp');temp.write_bytes(data);temp.replace(path)
            parts.append({'name':name,'bytes':len(data),'sha256':digest})
    if not parts:raise ValueError('Empty history database')
    manifest={'version':1,'compressed_bytes':packed.stat().st_size,'parts':parts}
    temp=destination/'manifest.tmp';temp.write_text(json.dumps(manifest,indent=2)+'\n')
    temp.replace(destination/'manifest.json')
    # Only obsolete generated parts, never source evidence or the legacy database.
    retained={p['name'] for p in parts}
    for path in destination.glob('*.gzpart'):
        if path.name not in retained:path.unlink()
    return manifest


class PartsReader(io.RawIOBase):
    def __init__(self, directory):
        self.directory=Path(directory)
        manifest=json.loads((self.directory/'manifest.json').read_text())
        self.parts=manifest['parts']
        if manifest.get('version')!=1 or not self.parts or sum(p['bytes'] for p in self.parts)!=manifest['compressed_bytes']:
            raise ValueError('Invalid history manifest')
        for part in self.parts:
            if not re.fullmatch(r'\d{4}-[a-f0-9]{64}\.gzpart',part['name']):raise ValueError('Invalid history part name')
            path=self.directory/part['name']
            if path.is_symlink() or path.stat().st_size!=part['bytes']:raise ValueError('Missing or truncated history part')
        self.index=0;self.source=None;self.digest=None

    def readable(self):return True

    def readinto(self, buffer):
        while self.index<len(self.parts):
            if self.source is None:
                self.source=(self.directory/self.parts[self.index]['name']).open('rb')
                self.digest=hashlib.sha256()
            count=self.source.readinto(buffer)
            if count:
                self.digest.update(memoryview(buffer)[:count]);return count
            self.source.close();self.source=None
            if self.digest.hexdigest()!=self.parts[self.index]['sha256']:raise ValueError('History part checksum mismatch')
            self.index+=1
        return 0

    def close(self):
        if self.source:self.source.close()
        super().close()


def available(directory):
    root=Path(directory)
    return (root/'database_parts/manifest.json').is_file() or (root/'auction_history.sqlite.gz').is_file()


def unpack(directory, target):
    root=Path(directory)
    if (root/'database_parts/manifest.json').exists():
        with PartsReader(root/'database_parts') as raw, io.BufferedReader(raw) as stream:
            with gzip.GzipFile(fileobj=stream,mode='rb') as source:
                shutil.copyfileobj(source,target,length=1024*1024)
    else:
        with gzip.open(root/'auction_history.sqlite.gz','rb') as source:
            shutil.copyfileobj(source,target,length=1024*1024)
