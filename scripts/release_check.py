#!/usr/bin/env python3
"""Check the exact public allowlist, then optionally build a text-only ZIP.

No runtime workspaces, photographs, hidden caches or Git history are packaged.
This is a repeatable screening aid, not a proof of all possible private data.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {'.git', '.venv', '__pycache__', '.pytest_cache'}
PATTERNS = {
    'personal-home': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'external-volume': re.compile(r'/' + r'Volumes/[^\s"\x27]+'),
    'private-site': re.compile(r'https?://[^\s/]+\.chatgpt\.site'),
    'camera-filename': re.compile(r'\b(?:DSC_[0-9]{4}|L[0-9]{7})\b'),
    'private-key': re.compile(r'^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', re.M),
    'api-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{32,})\b'),
}


def check(root=ROOT):
    allowed = json.loads((root / 'release-files.json').read_text())
    if len(allowed) != len(set(allowed)):
        raise ValueError('Duplicate allowlist path')
    actual = set()
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlink in release: ' + str(relative))
        if path.is_file():
            actual.add(relative.as_posix())
    if actual != set(allowed):
        raise ValueError('Allowlist mismatch: ' + repr(sorted(actual.symmetric_difference(allowed))))
    hashes = {}
    for name in allowed:
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Unsafe allowlist path')
        data = path.read_bytes()
        text = data.decode('utf-8')
        if '\x00' in text:
            raise ValueError('Binary content: ' + name)
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                raise ValueError(label + ': ' + name)
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', text):
                if '://' in target or target.startswith('#'):
                    continue
                destination = (path.parent / target.split('#')[0]).resolve()
                if not destination.is_relative_to(root.resolve()) or not destination.exists():
                    raise ValueError('Broken/outside documentation link in ' + name + ': ' + target)
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def build(output, hashes):
    output = Path(output).absolute()
    if output.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Archive must be outside package')
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, expected in hashes.items():
            data = (ROOT / name).read_bytes()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('File changed during packaging: ' + name)
            info = zipfile.ZipInfo('darkroom-finish/' + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError('Archive CRC failed')
    return {'archive_sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'bytes': output.stat().st_size}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip')
    args = parser.parse_args()
    hashes = check()
    result = {'pass': True, 'files': len(hashes), 'text_only': True, 'file_sha256': hashes}
    if args.zip:
        result.update(build(args.zip, hashes))
    print(json.dumps(result, indent=2))
