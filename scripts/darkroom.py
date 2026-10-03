#!/usr/bin/env python3
"""Standalone local RAW workspace CLI. No network calls or model API keys."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import uuid

PACKAGE = Path(__file__).resolve().parents[1]
RAW_EXTENSIONS = {'.nef', '.dng', '.cr2', '.cr3', '.arw', '.raf', '.orf', '.rw2', '.pef'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def photoshop_app(explicit=None):
    if explicit:
        candidates = [Path(explicit).expanduser().absolute()]
    else:
        candidates = sorted(Path('/Applications').glob('Adobe Photoshop*/*.app'))
    valid = []
    for app in candidates:
        try:
            info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            if info.get('CFBundleIdentifier') == 'com.adobe.Photoshop':
                valid.append((app, info.get('CFBundleShortVersionString', 'unknown')))
        except (OSError, plistlib.InvalidFileException):
            continue
    require(len(valid) == 1, 'Select one installed Photoshop with --photoshop-app (none or multiple found)')
    return valid[0]


def doctor(explicit=None):
    report = {'python': platform.python_version(), 'system': platform.system(),
              'architecture': platform.machine(), 'ready': False,
              'automation_permission': 'not_tested', 'raw_profiles': 'not_fully_frozen',
              'external_transfers': []}
    try:
        require(sys.version_info >= (3, 11), 'Python 3.11+ required')
        require(platform.system() == 'Darwin', 'Rendering currently requires macOS')
        require(shutil.which('osascript'), 'osascript is missing')
        app, version = photoshop_app(explicit)
        report.update(photoshop_app=str(app), photoshop_version=version)
        acr = Path('/Library/Application Support/Adobe/Plug-Ins/CC/File Formats/Camera Raw.plugin/Contents/Info.plist')
        require(acr.is_file(), 'Camera Raw plug-in was not found in the supported location')
        report['camera_raw_version'] = plistlib.loads(acr.read_bytes()).get('CFBundleShortVersionString', 'unknown')
        report['ready'] = True
    except ValueError as error:
        report['error'] = str(error)
    return report


def local_path(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'Workspace path must be relative')
    result = root / p
    require(result.resolve().is_relative_to(root), 'Workspace path escapes its root')
    current = root
    for part in p.parts:
        current /= part
        require(not current.is_symlink(), 'Symlink in workspace path')
    return result


def workspace(value):
    root = Path(value).expanduser().absolute()
    require(root.resolve() == root, 'Workspace must not use symlinks')
    config = json.loads(local_path(root, 'workspace.json').read_text())
    require(config.get('format') == 'darkroom-workspace/1', 'Not a darkroom workspace')
    for name, expected in config['runtime_hashes'].items():
        require(sha(local_path(root, name)) == expected, 'Runtime changed; use a new workspace for this version')
    return root, config


def init_workspace(value):
    root = Path(value).expanduser().absolute()
    require(root.resolve() == root, 'Workspace must not use symlinks')
    require(not root.exists(), 'Workspace already exists; choose a new directory')
    require(not root.is_relative_to(PACKAGE), 'Keep private workspaces outside the installed skill')
    hashes = {}
    for source in sorted((PACKAGE / 'runtime').rglob('*')):
        require(not source.is_symlink(), 'Runtime package contains a symlink')
        if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc':
            continue
        name = source.relative_to(PACKAGE / 'runtime')
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[str(name)] = sha(destination)
    save(root / 'workspace.json', {'format': 'darkroom-workspace/1', 'release': '0.1.0-alpha.1', 'runtime_hashes': hashes})
    return {'workspace': str(root), 'private': True}


def ingest(value, source_value, consent):
    root, _ = workspace(value)
    require(consent.strip(), 'Supply the actual user authorization text')
    source = Path(source_value).expanduser().absolute()
    require(source.resolve() == source and source.is_file(), 'Source must be one regular file without symlinks')
    require(source.suffix.lower() in RAW_EXTENSIONS, 'Select one supported RAW file')
    require(not source.is_relative_to(root), 'Select the external original, not workspace output')
    digest = sha(source)
    folder = local_path(root, 'staging/source/' + digest)
    auth_path = local_path(root, 'runs/authorization/' + digest + '.json')
    staged = local_path(root, str((folder / ('frame' + source.suffix.lower())).relative_to(root)))
    if not staged.exists():
        folder.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(source, staged)
    require(sha(staged) == digest and sha(source) == digest, 'Source or working copy changed during ingest')
    if not auth_path.exists():
        save(auth_path, {'text': consent, 'source': str(source), 'source_sha256': digest,
                         'purpose': 'Local photo editing only; no network transfer'})
    return {'source_id': digest, 'staged': str(staged.relative_to(root)), 'authorization': str(auth_path.relative_to(root))}


def parameters_card(root, parameters):
    require(isinstance(parameters, dict) and bool(parameters), 'Parameters must be a nonempty JSON object')
    registry = json.loads((root / 'registries/adobe-operation-registry-v1.json').read_text())
    fields = {o['field']: o for o in registry['operations'] if o.get('field') and o['evidence']['executor_write']['status'] == 'supported'}
    domains = {d['registry_id']: d for d in registry['enum_domains']}
    rules = []
    for field, value in parameters.items():
        require(field in fields, 'Unknown or unavailable field: ' + field)
        op = fields[field]
        if op['value_type'] == 'enum':
            ref = op['enum_domain_ref']
            require(value in domains[ref['registry_id']]['values'], 'Invalid enum: ' + field)
            scalar = {'type': 'enum', 'value': value, 'domain_ref': ref}
        elif op['value_type'] == 'curve':
            scalar = {'type': 'curve', 'points': value}
        else:
            require(isinstance(value, str), 'Use canonical decimal strings for: ' + field)
            scalar = {'type': 'decimal', 'value': value}
        rules.append({'field': field, 'value_spec': {'kind': 'absolute', 'unit': op.get('native_unit') or 'unit:none', 'value': scalar},
                      'allowed_range': op.get('native_range'), 'rationale': 'Chosen for this image; inspect the actual result.'})
    return {'schema_version': 'technique-card/v1', 'card_id': 'C01_PHOTO_PLAN', 'version': '0.1.0', 'status': 'candidate',
            'craft_scope': ['single-raw'], 'style_scope': ['user-directed'],
            'evidence_refs': [{'source': 'references/operations.md', 'role': 'compiler-contract', 'license_status': 'project-authored',
                               'extracted_principle': 'Admission and repeat pixels do not establish artistic quality.'}],
            'preconditions': ['source-authorized', 'inspect-baseline'], 'measurements': [], 'parameter_rules': rules,
            'mask_recipe': None, 'order_before': [], 'order_after': [], 'stop_conditions': ['source-changed', 'render-failed'],
            'failure_modes': [{'predicate': 'visible-artifacts', 'action': 'stop-and-review'}],
            'forbidden_operations': ['generative_fill', 'liquify'], 'expected_effects': ['image-specific-intent'],
            'quality_checks': ['G0', 'G1', 'G2'], 'golden_cases': []}


def prepare(value, source_id, parameters_file, intent):
    root, _ = workspace(value)
    require(len(source_id) == 64 and all(c in '0123456789abcdef' for c in source_id), 'Invalid source id')
    require(intent.strip(), 'State the visual intent for this version')
    auth_path = local_path(root, 'runs/authorization/' + source_id + '.json')
    auth = json.loads(auth_path.read_text())
    require(sha(Path(auth['source'])) == source_id, 'Original changed since ingest')
    sources = list(local_path(root, 'staging/source/' + source_id).glob('frame.*'))
    require(len(sources) == 1, 'Expected one staged RAW')
    staged = local_path(root, str(sources[0].relative_to(root)))
    parameters = json.loads(Path(parameters_file).read_text())
    # Pin the common controls rather than inheriting the previous photo's sliders.
    baseline = json.loads((PACKAGE / 'examples/neutral.json').read_text())
    baseline.update(parameters)
    card = parameters_card(root, baseline)
    run = 'trial-' + uuid.uuid4().hex[:12]
    card_path = local_path(root, 'knowledge/cards/' + run + '.json')
    theme_path = local_path(root, 'knowledge/themes/' + run + '.manifest.json')
    inventory = local_path(root, 'runs/plans/' + run + '-inventory.json')
    request_path = local_path(root, 'runs/plans/' + run + '-request.json')
    plan_path = local_path(root, 'runs/plans/' + run + '-plan.json')
    save(card_path, card)
    save(theme_path, {'cards': [run + '.json'], 'intents': {'PHOTO': {'statement': intent}}})
    save(inventory, {'files': [{'path': staged.name, 'sha256': source_id}]})
    ref = {'path': str(staged.relative_to(root)), 'sha256': source_id}
    request = {'source': ref, 'authorization': {'text': auth['text'], 'message_ref': 'local-authorization:' + source_id,
               'source_ref': {'path': str(auth_path.relative_to(root)), 'sha256': sha(auth_path)}, 'pointer': ['text'], 'source': ref},
               'argv': ['--theme', run, '--candidates', 'PHOTO:frame', '--run-id', run,
                        '--out-dir', 'output/' + run, '--album', str(staged.parent), '--raw-subdir', '',
                        '--ext', staged.suffix, '--inventory', str(inventory.relative_to(root)), '--allow-candidate']}
    save(request_path, request)
    subprocess.run([sys.executable, '-B', '-m', 'darkroom.local_trial', 'prepare', '--request', str(request_path), '--plan', str(plan_path)], cwd=root, check=True, capture_output=True, text=True)
    return {'plan': str(plan_path.relative_to(root)), 'intent': intent, 'attempt_reserved': True}


def render(value, plan_value, explicit):
    root, _ = workspace(value)
    report = doctor(explicit)
    require(report['ready'], report.get('error', 'Environment not ready'))
    plan_path = local_path(root, plan_value)
    plan = json.loads(plan_path.read_text())
    auth = json.loads(local_path(root, plan['request']['authorization']['source_ref']['path']).read_text())
    source = Path(auth['source'])
    require(sha(source) == auth['source_sha256'], 'Original changed before render')
    env = dict(os.environ, DARKROOM_PHOTOSHOP_APP=report['photoshop_app'])
    try:
        subprocess.run([sys.executable, '-B', str(root / 'darkroom/ps_acr/card_pipeline.py'),
                        *plan['request']['argv'], '--local-trial-plan', str(plan_path)], cwd=root, env=env, check=True)
    finally:
        require(sha(source) == auth['source_sha256'], 'STOP: original changed during render')
    return {'rendered': True, 'visual_review': 'NOT_PERFORMED', 'quality_acceptance': False,
            'output': plan['binding']['directories'][1], 'external_transfers': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('doctor'); check.add_argument('--photoshop-app')
    init = sub.add_parser('init'); init.add_argument('--workspace', required=True)
    add = sub.add_parser('ingest'); add.add_argument('--workspace', required=True); add.add_argument('--source', required=True); add.add_argument('--authorization', required=True)
    plan = sub.add_parser('prepare'); plan.add_argument('--workspace', required=True); plan.add_argument('--source-id', required=True); plan.add_argument('--parameters', required=True); plan.add_argument('--intent', required=True)
    go = sub.add_parser('render'); go.add_argument('--workspace', required=True); go.add_argument('--plan', required=True); go.add_argument('--photoshop-app')
    args = parser.parse_args()
    if args.command == 'doctor':
        result = doctor(args.photoshop_app)
    elif args.command == 'init':
        result = init_workspace(args.workspace)
    elif args.command == 'ingest':
        result = ingest(args.workspace, args.source, args.authorization)
    elif args.command == 'prepare':
        result = prepare(args.workspace, args.source_id, args.parameters, args.intent)
    else:
        result = render(args.workspace, args.plan, args.photoshop_app)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == 'doctor' and not result['ready'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        print('REFUSED: ' + (detail or str(error)), file=sys.stderr)
        sys.exit(1)
