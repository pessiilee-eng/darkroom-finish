"""Single-source LOCAL_ONLY trials. This module authorizes; card_pipeline renders.

Small source-hash records conserve attempts across names/plans. Legacy history is
read only at preparation/refresh; registered sources reserve in ReviewStore too.
No visual approval, model calls, image decoder or alternate renderer lives here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

PROJECT = Path(__file__).resolve().parents[1]
HASH = re.compile(r"[a-f0-9]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
VALUE_FLAGS = {'--theme', '--candidates', '--run-id', '--out-dir', '--album', '--raw-subdir',
               '--ext', '--inventory', '--raster-python', '--review-crop-plan', '--acr-geometry-plan'}
REQUIRED_FLAGS = VALUE_FLAGS - {'--raster-python', '--review-crop-plan', '--acr-geometry-plan'}
BOOLEAN_FLAGS = {'--preview-only', '--allow-candidate'}


def need(condition, reason):
    if not condition:
        raise ValueError('LOCAL_TRIAL_REFUSED: ' + reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def safe_path(root, value, prefix=None, exists=False):
    need(isinstance(value, str) and bool(value), 'path_missing')
    given = Path(value)
    need('..' not in given.parts, 'path_traversal')
    path = given if given.is_absolute() else root / given
    need(path.is_relative_to(root) and path != root, 'path_outside_project')
    rel = path.relative_to(root)
    need(prefix is None or rel.parts[0] == prefix, 'path_outside_' + str(prefix))
    current = root
    for part in rel.parts:
        current = current / part
        need(not current.is_symlink(), 'symlink_path')
    need(not exists or path.is_file(), 'file_missing: ' + str(rel))
    return path


def file_ref(root, value, prefix=None):
    path = safe_path(root, value, prefix, exists=True)
    return {'path': str(path.relative_to(root)), 'sha256': digest(path)}


def verify_ref(root, ref, prefix=None):
    need(isinstance(ref, dict) and HASH.fullmatch(str(ref.get('sha256', ''))), 'file_hash_missing')
    actual = file_ref(root, ref.get('path'), prefix)
    need(actual == ref, 'frozen_file_changed: ' + str(ref.get('path')))
    return safe_path(root, ref['path'])


def write_json(path, value, exclusive=False):
    data = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if exclusive:
        with path.open('x') as handle:
            handle.write(data)
        return
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x') as handle:
            handle.write(data)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def source_state_path(root, source_hash):
    need(HASH.fullmatch(str(source_hash)), 'source_hash_invalid')
    return safe_path(root, f'runs/local-trial/sources/{source_hash}.json')


@contextmanager
def locked_state(root, source_hash):
    path = source_state_path(root, source_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = safe_path(root, str(path.with_suffix('.lock')))
    with lock.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('LOCAL_TRIAL_REFUSED: source_busy_retry_same_plan') from None
        yield path


def head_token(root):
    path = safe_path(root, 'runs/review-workflow/head.json')
    if not path.exists():
        need(not path.parent.exists(), 'legacy_ledger_incomplete')
        return None
    return file_ref(root, str(path))


# ReviewStore remains the authority for registered budgets. read() is called once
# for import/refresh; reserve() has its own transactional read, never an init().
def legacy_snapshot(root, source_hash, photo_id=None, identity=None):
    need(head_token(root) is None, 'private_history_not_supported_by_public_release')
    return {'photo_id': None, 'budgets': None, 'history': [], 'reservation': None}


def parse_argv(argv):
    need(isinstance(argv, list) and all(isinstance(x, str) for x in argv), 'argv_invalid')
    values, i = {}, 0
    while i < len(argv):
        flag = argv[i]
        need(flag in VALUE_FLAGS | BOOLEAN_FLAGS and flag not in values, 'unknown_or_duplicate_argument')
        if flag in BOOLEAN_FLAGS:
            values[flag] = True
        else:
            i += 1
            need(i < len(argv) and not argv[i].startswith('--'), 'argument_value_missing')
            values[flag] = argv[i]
        i += 1
    need(REQUIRED_FLAGS <= values.keys(), 'required_argument_missing')
    for key in ('--theme', '--run-id'):
        need(NAME.fullmatch(values[key]), 'name_invalid')
    need(re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9][A-Za-z0-9_.-]*', values['--candidates']), 'single_frame_required')
    need(values['--ext'].upper() in {'.NEF', '.DNG', '.CR2', '.CR3', '.ARW', '.RAF', '.ORF', '.RW2', '.PEF'}, 'raw_extension_required')
    return values


def authorization(root, request):
    auth = request.get('authorization', {})
    need(isinstance(auth.get('text'), str) and auth['text'].strip(), 'authorization_text_missing')
    need(isinstance(auth.get('message_ref'), str) and auth['message_ref'].strip(), 'authorization_message_ref_missing')
    file = verify_ref(root, auth.get('source_ref'), 'runs')
    pointer = auth.get('pointer', [])
    need(isinstance(pointer, list), 'authorization_pointer_invalid')
    value = json.loads(file.read_text()) if pointer else file.read_text()
    for key in pointer:
        need(isinstance(key, (str, int)) and not isinstance(key, bool), 'authorization_pointer_invalid')
        value = value[key]
    need(value == auth['text'], 'authorization_original_text_mismatch')
    need(auth.get('source') == request.get('source'), 'authorization_source_scope_mismatch')
    return auth


def dependency_files(root, values, theme, recipe):
    files = {'darkroom/local_trial.py', 'darkroom/ps_acr/card_pipeline.py', 'darkroom/ps_acr/minimal_loop.py',
             'darkroom/cards/validate.py', 'scripts/operation_registry.py', 'scripts/verify_ai_darkroom_contracts.py',
             'registries/adobe-operation-registry-v1.json', 'registries/adobe-unit-registry-v1.json',
             'schemas/adobe-operation-registry-v1.schema.json', 'schemas/formula-dsl-v1.schema.json',
             'schemas/formula-lookup-table-v1.schema.json', 'schemas/technique-card-v1.schema.json',
             f"knowledge/themes/{values['--theme']}.manifest.json", 'darkroom/knowledge.py'}
    files.add(theme['public_plan'])
    from darkroom.knowledge import load as load_knowledge
    manifest, _, _ = load_knowledge(root / 'knowledge/library')
    files.update('knowledge/library/' + name for name in ['manifest.json', *manifest['files']])
    for card in theme['cards']:
        path = safe_path(root, 'knowledge/cards/' + card, 'knowledge', exists=True)
        need(path.is_relative_to(root / 'knowledge/cards'), 'card_path_outside_cards')
        files.add(str(path.relative_to(root)))
    if values.get('--review-crop-plan'):
        files.update({values['--review-crop-plan'], 'darkroom/review_crop.py', 'darkroom/ps_acr/crop_derivative.py'})
    files.add('darkroom/acr_geometry.py')
    if values.get('--acr-geometry-plan'):
        files.add(values['--acr-geometry-plan'])
    need(recipe is None, 'raster_recipes_not_in_public_runtime')
    if recipe:
        modules = {'local.harmonic_tone_balance': 'local_tone_balance.py', 'local.skin_control_field': 'local_skin_field.py',
                   'local.skin_texture_smoothing': 'local_skin_texture.py', 'local.sun_glow': 'local_sun_glow.py',
                   'local.sampled_frequency_repair': 'local_sampled_repair.py', 'local.same_source_restore': 'local_same_source_restore.py',
                   'local.tonal_brush': 'local_tonal_brush.py', 'local.spatial_light': 'local_spatial_light.py',
                   'local.same_image_clone': 'local_same_image_clone.py'}
        need(recipe.get('operation_id') in modules, 'unsupported_local_operation')
        names = {modules[recipe['operation_id']], 'local_tone_balance.py'}
        if recipe['operation_id'] == 'local.tonal_brush':
            names.update({'local_skin_field.py', 'local_same_source_restore.py'})
        if recipe['operation_id'] == 'local.same_image_clone':
            names.add('local_same_source_restore.py')
        files.update('darkroom/ps_acr/' + name for name in names)
    return [file_ref(root, name) for name in sorted(files)]


def compile_request(root, request, pipeline):
    authorization(root, request)  # Must precede reading the exact RAW bytes.
    values = parse_argv(request.get('argv'))
    gid, stem = values['--candidates'].split(':')
    source_path = safe_path(root, str(Path(values['--album']) / values['--raw-subdir'] / (stem + values['--ext'])), 'staging', True)
    need(file_ref(root, str(source_path)) == request.get('source'), 'argv_source_mismatch')
    source = verify_ref(root, request['source'], 'staging')
    inventory_ref = file_ref(root, values['--inventory'], 'runs')
    inventory = json.loads(verify_ref(root, inventory_ref).read_text())
    key = (values['--raw-subdir'] + '/' if values['--raw-subdir'] else '') + source.name
    need(inventory.get('files') == [{'path': key, 'sha256': request['source']['sha256']}], 'inventory_must_bind_exact_single_source')
    theme_path = safe_path(root, f"knowledge/themes/{values['--theme']}.manifest.json", 'knowledge', True)
    theme = json.loads(theme_path.read_text())
    need(isinstance(theme.get('cards'), list) and len(theme['cards']) > 0, 'theme_cards_missing')
    need(not theme.get('intents', {}).get(gid, {}).get('overrides'), 'public_plan_overrides_must_be_in_frozen_card')
    # Check card names before the existing compiler opens them.
    for name in theme['cards']:
        safe_path(root, 'knowledge/cards/' + name, 'knowledge', True)
    cards = pipeline.load_cards(theme, bool(values.get('--allow-candidate')))
    params = pipeline.resolve_params(cards, theme.get('intents', {}).get(gid, {}).get('overrides', {}))
    mask = pipeline.resolve_mask_graph(cards)
    recipe = pipeline.resolve_postprocess_recipe(cards)
    from darkroom.acr_geometry import merge_geometry, validate_geometry_plan, read_raw_orientation
    geometry = None
    if values.get('--acr-geometry-plan'):
        need(not (recipe or values.get('--preview-only') or values.get('--review-crop-plan')), 'native_geometry_requires_direct_full_raw_without_raster_or_jpeg_crop')
        geometry = validate_geometry_plan(json.loads(safe_path(root, values['--acr-geometry-plan'], 'runs', True).read_text()))
    orientation = read_raw_orientation(source) if geometry else None
    from darkroom.knowledge import validate_receipt
    need(len(theme['cards']) == 1, 'public_plan_requires_one_frozen_card')
    receipt_path = safe_path(root, theme.get('public_plan', ''), 'runs', True)
    receipt = json.loads(receipt_path.read_text())
    raw_card = json.loads(safe_path(root, 'knowledge/cards/' + theme['cards'][0], 'knowledge', True).read_text())
    validate_receipt(root, receipt, request['source']['sha256'], raw_card, geometry)
    if receipt['role'] == 'edit':
        need(theme['intents'][gid]['statement'] == receipt['knowledge_plan']['intent'], 'knowledge_intent_mismatch')
    params = merge_geometry(params, geometry, orientation)
    need(not (recipe and values.get('--preview-only')), 'local_recipe_requires_full_replay')
    need(not values.get('--review-crop-plan'), 'jpeg_crop_not_in_public_runtime')
    crop = None
    if values.get('--review-crop-plan'):
        from darkroom.review_crop import validate_crop_plan
        crop = validate_crop_plan(json.loads(safe_path(root, values['--review-crop-plan'], 'runs', True).read_text()))
    out = safe_path(root, values['--out-dir'], 'output')
    run = safe_path(root, 'runs/' + values['--run-id'], 'runs')
    need(not run.is_relative_to(root / 'runs/local-trial') and not run.is_relative_to(root / 'runs/review-workflow'), 'reserved_run_directory')
    render = safe_path(root, f"staging/render/{gid}-{values['--theme']}-{values['--run-id']}", 'staging')
    need(not source.is_relative_to(render), 'source_overlaps_render_directory')
    outputs = [out / f'{gid}-{stem}.jpg', out / f'{gid}-{stem}.manifest.json', run / 'evidence.json', run / 'card-render.jsx',
               render / source.name, render / f'{stem}.xmp']
    if not values.get('--preview-only'):
        outputs += [out / f'{gid}-{stem}.tif', run / f'{gid}-{stem}-replay.tif']
    if crop:
        outputs += [out / f'{gid}-{stem}{suffix}' for suffix in ('-crop.jpg', '-crop-review-1600.jpg', '-crop.json')]
    sidecars = []
    for suffix in ('.xmp', '.XMP'):
        p = safe_path(root, str(source.with_suffix(suffix)), 'staging')
        sidecars.append({'path': str(p.relative_to(root)), 'sha256': digest(p) if p.exists() else None})
    runtime = Path(values.get('--raster-python', sys.executable)).resolve()
    need(runtime.is_file() and os.access(runtime, os.X_OK), 'python_runtime_invalid')
    return {'source': request['source'], 'inventory': inventory_ref, 'parameters': params, 'mask_graph': mask,
            'postprocess_recipe': recipe, 'crop_plan': crop, 'acr_geometry_plan': geometry, 'acr_geometry_orientation': orientation, 'source_sidecars': sidecars,
            'xmp_sha256': hashlib.sha256(pipeline.render_xmp_sidecar(params, mask, raw_orientation=orientation).encode()).hexdigest(),
            'dependencies': dependency_files(root, values, theme, recipe),
            'runtime': {'path': str(runtime), 'sha256': digest(runtime)},
            'directories': [str(x.relative_to(root)) for x in (run, out, render)],
            'outputs': [str(x.relative_to(root)) for x in outputs]}


def verify_binding(root, plan):
    authorization(root, plan['request'])
    verify_ref(root, plan['request_ref'], 'runs')
    binding = plan['binding']
    for ref in [binding['source'], binding['inventory'], *binding['dependencies']]:
        verify_ref(root, ref)
    for ref in binding['source_sidecars']:
        p = safe_path(root, ref['path'], 'staging')
        need((digest(p) if p.exists() else None) == ref['sha256'], 'source_sidecar_changed')
    runtime = binding['runtime']
    need(digest(runtime['path']) == runtime['sha256'], 'python_runtime_changed')


def budget_view(snapshot):
    budgets = snapshot.get('budgets')
    if budgets is None:
        return {'used': 0, 'limit': 3, 'state': 'active'}
    scope = budgets.get('activeWindow') or budgets
    count = scope.get('creativeAttempts', {})
    need(budgets.get('state') not in ('stopped', 'STOPPED') and scope.get('state') not in ('stopped', 'STOPPED'), 'historical_stop_preserved')
    used, limit = count.get('used'), count.get('limit')
    need(type(used) is int and type(limit) is int and 0 <= used <= limit, 'historical_budget_unknown')
    cumulative = snapshot.get('cumulative_creative_attempts')
    if cumulative is not None:
        total_used, total_limit = cumulative.get('used'), cumulative.get('limit')
        need(type(total_used) is int and type(total_limit) is int and
             0 <= total_used <= total_limit and total_used >= used and
             total_limit - total_used == limit - used and cumulative.get('state') == scope.get('state'),
             'historical_cumulative_budget_unknown')
        used, limit = total_used, total_limit
    else:
        need(not budgets.get('activeWindow'), 'historical_cumulative_budget_missing')
    return {'used': used, 'limit': limit, 'state': scope.get('state')}


def recover_interrupted(state):
    """Only a demonstrably dead process loses its running claim; attempts stay used."""
    changed = False
    for record in state['plans'].values():
        if record['status'] != 'running':
            continue
        pid = record.get('process_pid')
        need(type(pid) is int and pid > 0, 'running_process_identity_unknown')
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            record.update({'status': 'failed', 'exit_code': 1, 'quality_acceptance_passed': False,
                           'errors': ['execution_process_disappeared_interrupted'], 'outputs': []})
            changed = True
        except PermissionError:
            raise ValueError('LOCAL_TRIAL_REFUSED: running_process_cannot_be_checked') from None
    return changed


def fresh_outputs(root, binding):
    for directory in binding['directories']:
        path = safe_path(root, directory)
        need(not path.exists(), 'fresh_directory_required: ' + directory)


def verify_window(root, window):
    verify_ref(root, window['request_ref'], 'runs')
    authorization(root, window['request'])


def authorize_window(root, request_path):
    """Append one evidenced feedback attempt; never reset or migrate a budget."""
    root = Path(root).resolve()
    request_ref = file_ref(root, str(request_path), 'runs')
    request = json.loads(verify_ref(root, request_ref).read_text())
    auth = authorization(root, request)
    verify_ref(root, request['source'], 'staging')
    need(type(request.get('additional_attempts')) is int and request['additional_attempts'] == 1,
         'feedback_window_requires_exactly_one_attempt')
    need(isinstance(request.get('reason'), str) and request['reason'].strip(), 'feedback_reason_missing')
    with locked_state(root, request['source']['sha256']) as state_path:
        need(state_path.is_file(), 'existing_source_record_required')
        state = json.loads(state_path.read_text())
        need(state['source_sha256'] == request['source']['sha256'], 'window_source_mismatch')
        need(state.get('origin_unregistered') is True and state['legacy_photo_id'] is None,
             'registered_source_requires_legacy_authorization')
        current_head = head_token(root)
        if state['head_token'] != current_head:
            snapshot = legacy_snapshot(root, state['source_sha256'])
            need(snapshot['photo_id'] is None, 'registered_source_requires_legacy_authorization')
        need(all(p['status'] != 'running' for p in state['plans'].values()), 'source_already_running')
        old_plans = [json.loads(verify_ref(root, p['plan_ref'], 'runs').read_text())
                     for p in state['plans'].values()]
        need(request['source'] in [p['binding']['source'] for p in old_plans], 'window_source_mismatch')
        need(all(p['request']['authorization']['message_ref'] != auth['message_ref'] for p in old_plans),
             'fresh_feedback_evidence_required')
        windows = state.get('authorization_windows', [])
        for window in windows:
            verify_window(root, window)
            previous = window['request']['authorization']
            need(previous['message_ref'] != auth['message_ref'] and
                 (previous['source_ref']['sha256'], previous.get('pointer', [])) !=
                 (auth['source_ref']['sha256'], auth.get('pointer', [])), 'authorization_evidence_already_used')
        budget = state['budget']
        need(budget.get('state') == 'active', 'historical_stop_preserved')
        need(type(budget['used']) is int and type(budget['limit']) is int and
             budget['used'] == budget['limit'] and budget['used'] >= 3, 'exhausted_budget_required')
        window = {'id': request_ref['sha256'], 'request_ref': request_ref, 'request': request,
                  'used_at_authorization': budget['used'], 'limit_before': budget['limit'],
                  'limit_after': budget['limit'] + 1, 'verified_legacy_head': current_head}
        need(head_token(root) == current_head, 'legacy_head_changed_retry_same_authorization')
        verify_window(root, window)
        budget['limit'] = window['limit_after']
        state.setdefault('authorization_windows', []).append(window)
        write_json(state_path, state)
    return {'window_id': window['id'], 'source': request['source'], 'used': budget['used'],
            'limit': budget['limit'], 'additional_attempts': 1, 'new_attempt_reserved': False}


def prepare(root, request_path, plan_path, pipeline):
    root = Path(root).resolve()
    request_path = safe_path(root, str(request_path), 'runs', True)
    request = json.loads(request_path.read_text())
    binding = compile_request(root, request, pipeline)
    plan_path = safe_path(root, str(plan_path), 'runs')
    if plan_path.exists():
        plan, _, _ = load_plan(root, plan_path)
        need(plan['request_ref'] == file_ref(root, str(request_path)) and plan['binding'] == binding, 'existing_plan_does_not_match_request')
        return plan
    need(not any(plan_path.is_relative_to(root / d) for d in binding['directories']), 'plan_inside_output_directory')
    fresh_outputs(root, binding)
    source_hash = binding['source']['sha256']
    with locked_state(root, source_hash) as state_path:
        state = json.loads(state_path.read_text()) if state_path.exists() else None
        for window in (state or {}).get('authorization_windows', []):
            verify_window(root, window)
        if state and recover_interrupted(state):
            write_json(state_path, state)
        need(not state or all(p['status'] != 'running' for p in state['plans'].values()), 'source_already_running')
        snapshot = None
        if state is None or state['head_token'] != head_token(root):
            snapshot = legacy_snapshot(root, source_hash)
        if state is None:
            budget = budget_view(snapshot)
            state = {'version': 1, 'source_sha256': source_hash, 'legacy_photo_id': snapshot['photo_id'],
                     'legacy_history': snapshot['history'], 'budget': budget, 'local_attempts': 0,
                     'origin_unregistered': snapshot['photo_id'] is None, 'plans': {}, 'head_token': head_token(root)}
        elif snapshot:
            need(not (state['origin_unregistered'] and state['local_attempts'] and snapshot['photo_id']),
                 'local_history_must_be_merged_before_legacy_mode')
            need(snapshot['photo_id'] == state['legacy_photo_id'], 'source_registration_changed')
            if snapshot['photo_id']:
                budget = budget_view(snapshot)
                need(budget['used'] >= state['budget']['used'], 'budget_cannot_reset')
                state['budget'] = budget
            state['legacy_history'] = snapshot['history']
        plan_id = hashlib.sha256(json.dumps({'request_ref': file_ref(root, str(request_path)),
                    'plan_path': str(plan_path.relative_to(root)), 'binding': binding}, sort_keys=True).encode()).hexdigest()
        reservation = None
        previous = state['plans'].get(plan_id)
        prior_reservation = next((e for e in state['legacy_history'] if e.get('identity') == 'local-trial:' + plan_id), None)
        need(previous or prior_reservation or state['budget']['used'] < state['budget']['limit'], 'creative_budget_exhausted')
        fresh_outputs(root, binding)
        if prior_reservation:
            reservation = prior_reservation
        elif state['legacy_photo_id']:
            snapshot = legacy_snapshot(root, source_hash, state['legacy_photo_id'], 'local-trial:' + plan_id)
            state['budget'] = budget_view(snapshot)
            state['legacy_history'] = snapshot['history']
            reservation = snapshot['reservation']
            need(reservation and reservation['identity'] == 'local-trial:' + plan_id, 'legacy_reservation_missing')
        elif not previous:
            state['budget']['used'] += 1
        if not previous:
            state['local_attempts'] += 1
        state['head_token'] = head_token(root)
        plan = {'version': 1, 'id': plan_id, 'mode': 'LOCAL_ONLY', 'quality_acceptance_passed': False,
                'request': request, 'request_ref': file_ref(root, str(request_path)), 'binding': binding,
                'legacy_reservation_id': reservation['reservationId'] if reservation else None}
        window = previous.get('authorization_window') if previous else (state.get('authorization_windows') or [None])[-1]
        if window:
            plan['authorization_window'] = window
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_bytes = (json.dumps(plan, ensure_ascii=False, indent=2) + '\n').encode()
        state['plans'][plan_id] = {'plan_ref': {'path': str(plan_path.relative_to(root)), 'sha256': hashlib.sha256(plan_bytes).hexdigest()}, 'status': 'prepared',
                                   'head_token': state['head_token'], 'legacy_reservation_id': plan['legacy_reservation_id']}
        if window:
            state['plans'][plan_id]['authorization_window'] = window
        write_json(state_path, state)
        # Persist the consumed attempt first. Retrying this same request/path
        # reconstructs the same plan without reserving another attempt.
        write_json(plan_path, plan, exclusive=True)
    return plan


def load_plan(root, plan_path):
    path = safe_path(root, str(plan_path), 'runs', True)
    plan = json.loads(path.read_text())
    need(plan.get('version') == 1 and plan.get('mode') == 'LOCAL_ONLY' and plan.get('quality_acceptance_passed') is False, 'plan_mode_invalid')
    state_path = source_state_path(root, plan['binding']['source']['sha256'])
    need(state_path.is_file(), 'prepared_source_record_missing')
    state = json.loads(state_path.read_text())
    record = state['plans'].get(plan['id'])
    need(record is not None and record['plan_ref'] == file_ref(root, str(path)), 'plan_not_frozen_or_changed')
    verify_binding(root, plan)
    if plan.get('authorization_window'):
        verify_window(root, plan['authorization_window'])
    return plan, state, record


def refresh(root, plan_path):
    plan, _, _ = load_plan(root, plan_path)
    with locked_state(root, plan['binding']['source']['sha256']) as state_path:
        plan, state, record = load_plan(root, plan_path)
        need(record['status'] == 'prepared', 'only_prepared_plan_can_refresh')
        snapshot = legacy_snapshot(root, state['source_sha256'])
        need(snapshot['photo_id'] == state['legacy_photo_id'], 'local_history_must_be_merged_before_legacy_mode')
        if snapshot['photo_id']:
            budget = budget_view(snapshot)
            need(budget['used'] >= state['budget']['used'], 'budget_cannot_reset')
            need(any(e.get('reservationId') == record['legacy_reservation_id'] and e.get('identity') == 'local-trial:' + plan['id']
                     for e in snapshot['history']), 'original_reservation_missing')
            state['budget'] = budget
        state['legacy_history'] = snapshot['history']
        state['head_token'] = record['head_token'] = head_token(root)
        write_json(state_path, state)
    return {'plan_id': plan['id'], 'refreshed': True, 'new_attempt_reserved': False}


def begin(root, plan_path, argv):
    # Exact argv includes ordering/values; only the local authorization flag is removed.
    argv = list(argv)
    need(argv.count('--local-trial-plan') == 1, 'local_plan_argument_missing_or_duplicate')
    index = argv.index('--local-trial-plan')
    need(index + 1 < len(argv) and argv[index + 1] == str(plan_path), 'local_plan_argument_mismatch')
    del argv[index:index + 2]
    plan, _, _ = load_plan(root, plan_path)
    need(argv == plan['request']['argv'], 'exact_argv_mismatch')
    with locked_state(root, plan['binding']['source']['sha256']) as state_path:
        plan, state, record = load_plan(root, plan_path)
        if recover_interrupted(state):
            write_json(state_path, state)
        need(record['status'] == 'prepared', 'plan_already_started')
        need(all(p['status'] != 'running' for p in state['plans'].values()), 'source_already_running')
        need(record['head_token'] == head_token(root), 'legacy_head_changed_run_refresh_same_plan')
        fresh_outputs(root, plan['binding'])
        # Mark first: a crash cannot replay the same authorization or reset budget.
        record['status'] = 'running'
        record['process_pid'] = os.getpid()
        write_json(state_path, state)
        try:
            for directory in plan['binding']['directories']:
                path = safe_path(root, directory)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.mkdir(exist_ok=False)
        except (OSError, ValueError) as exc:
            record.update({'status': 'failed', 'exit_code': 1, 'quality_acceptance_passed': False,
                           'errors': [str(exc)], 'outputs': []})
            write_json(state_path, state)
            raise
    return plan


def finish(root, plan, exit_code):
    errors, outputs = [], []
    binding = plan['binding']
    manifest = manifest_path = None
    try:
        verify_binding(root, plan)
        for name in binding['outputs']:
            need(safe_path(root, name).is_file(), 'expected_output_missing: ' + name)
        manifest_path = next(safe_path(root, x) for x in binding['outputs'] if x.endswith('.manifest.json'))
        manifest = json.loads(manifest_path.read_text())
        need(manifest.get('quality_acceptance_passed') is False, 'trial_cannot_claim_quality_acceptance')
        need(manifest.get('transmission_facts', {}).get('external_transfer_mode') == 'LOCAL_ONLY', 'trial_transfer_mode_changed')
        need(manifest.get('source_sha256') == binding['source']['sha256'] and
             manifest.get('resolved_params') == binding['parameters'], 'manifest_binding_mismatch')
        need(manifest.get('acr_params_xmp_sha256') == binding['xmp_sha256'], 'manifest_xmp_binding_mismatch')
        if binding.get('acr_geometry_plan'):
            geometry = manifest.get('acr_geometry') or {}
            need(geometry.get('plan') == binding['acr_geometry_plan'], 'manifest_geometry_binding_mismatch')
            need(geometry.get('source_orientation') == binding['acr_geometry_orientation'], 'manifest_geometry_orientation_mismatch')
            if binding.get('mask_graph') is not None:
                need(manifest.get('mask_graph_sha256') == binding['mask_graph']['graph_sha256'] and
                     manifest.get('mask_transport_orientation') == binding['acr_geometry_orientation'], 'manifest_mask_transport_mismatch')
            need(geometry.get('dimension_gate_passed') is True or exit_code != 0, 'manifest_geometry_dimensions_failed')
            need(manifest.get('working_raw_sha256_after') == binding['source']['sha256'], 'working_raw_changed')
        need(manifest.get('render_pass') is True or exit_code != 0, 'manifest_render_failed')
        for name in binding['outputs']:
            outputs.append(file_ref(root, name))
    except (ValueError, OSError, KeyError, TypeError, AttributeError, StopIteration) as exc:
        errors.append(str(exc))
    code = exit_code or (1 if errors else 0)
    # Malformed/changed outputs remain untouched evidence, never a valid receipt.
    if isinstance(manifest, dict):
        if errors:
            manifest['render_pass'] = False
            manifest['quality_acceptance_passed'] = False
            if not isinstance(manifest.get('gates'), dict):
                manifest['gates'] = {}
            manifest['gates']['G1_params_frozen'] = False
        manifest['local_trial'] = {'plan_id': plan['id'], 'plan_mode': 'LOCAL_ONLY',
                                   'visual_review': 'NOT_PERFORMED', 'binding_intact': not errors, 'errors': errors}
        try:
            write_json(manifest_path, manifest)
            outputs = [file_ref(root, name) for name in binding['outputs']] if not errors else []
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            code = 1
    with locked_state(root, binding['source']['sha256']) as state_path:
        state = json.loads(state_path.read_text())
        record = state['plans'][plan['id']]
        need(record['status'] == 'running', 'finish_without_start')
        record.update({'status': 'rendered' if code == 0 else 'failed', 'exit_code': code,
                       'quality_acceptance_passed': False, 'errors': errors,
                       'outputs': outputs if not errors else []})
        write_json(state_path, state)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check', 'refresh', 'authorize-window'))
    parser.add_argument('--request')
    parser.add_argument('--plan')
    args = parser.parse_args()
    if args.command == 'authorize-window':
        need(args.request is not None and args.plan is None, 'window_requires_request_without_plan')
        print(json.dumps(authorize_window(PROJECT, args.request)))
        return
    need(args.plan is not None, 'plan_missing')
    if args.command == 'prepare':
        need(args.request is not None, 'request_missing')
        from darkroom.ps_acr import card_pipeline
        result = prepare(PROJECT, args.request, args.plan, card_pipeline)
        print(json.dumps({'plan_id': result['id'], 'plan': args.plan, 'mode': 'LOCAL_ONLY', 'quality_acceptance_passed': False}))
    elif args.command == 'refresh':
        print(json.dumps(refresh(PROJECT, args.plan)))
    else:
        plan, _, record = load_plan(PROJECT, args.plan)
        need(record['head_token'] == head_token(PROJECT), 'legacy_head_changed_run_refresh_same_plan')
        print(json.dumps({'plan_id': plan['id'], 'status': record['status'], 'quality_acceptance_passed': False}))


if __name__ == '__main__':
    main()
