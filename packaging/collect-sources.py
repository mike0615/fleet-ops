"""Retain exact upstream Python source distributions for the bundled runtime."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

lock, destination = map(Path, sys.argv[1:])
destination.mkdir(parents=True, exist_ok=True)
checksums = []
for line in lock.read_text().splitlines():
    name, version = line.split('==', 1)
    with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json', timeout=60) as response:
        metadata = json.load(response)
    candidates = [entry for entry in metadata['urls'] if entry['packagetype'] == 'sdist']
    if not candidates:
        raise RuntimeError(f'No source distribution: {name} {version}')
    entry = candidates[0]
    with urllib.request.urlopen(entry['url'], timeout=120) as response:
        content = response.read()
    digest = hashlib.sha256(content).hexdigest()
    if digest != entry['digests']['sha256']:
        raise RuntimeError(f'Source checksum mismatch: {name}')
    (destination / entry['filename']).write_bytes(content)
    checksums.append(f"{digest}  {entry['filename']}")
(destination / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')
