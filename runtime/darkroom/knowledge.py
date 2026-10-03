"""Portable research retrieval and source-bound planning; no network or model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

NEUTRAL = {'white_balance': 'AS_SHOT', 'exposure2012': '0', 'contrast2012': '0',
           'highlights2012': '0', 'shadows2012': '0', 'whites2012': '0', 'blacks2012': '0',
           'clarity2012': '0', 'dehaze': '0', 'vibrance': '0', 'saturation': '0',
           'point_curve_rgb': [{'input': '0', 'output': '0'}, {'input': '255', 'output': '255'}]}
SYNTHETIC_SHA256 = '66dc1e218b3da08fba6154f02ca5211af660a2558f292447631ad64764f3a1b7'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe(root, name):
    root = Path(root).absolute()
    p = Path(name)
    need(not p.is_absolute() and '..' not in p.parts and p.parts, 'Unsafe knowledge path')
    result = root / p
    need(root.resolve() == root and result.resolve().is_relative_to(root), 'Knowledge path escapes root')
    current = root
    for part in p.parts:
        current /= part
        need(not current.is_symlink(), 'Symlink in knowledge path')
    return result


def load(root):
    root = Path(root).absolute()
    path = safe(root, 'manifest.json')
    manifest = json.loads(path.read_text())
    need(manifest.get('schema') == 'darkroom-knowledge/1', 'Unsupported knowledge manifest')
    need(isinstance(manifest.get('files'), dict) and manifest['files'], 'Knowledge files missing')
    for name, expected in manifest['files'].items():
        need(digest(safe(root, name)) == expected, 'Knowledge changed: ' + name)
    for name in ('index.json', manifest['catalog']):
        need(name in manifest['files'], 'Unbound knowledge entrypoint')
    catalog = json.loads(safe(root, manifest['catalog']).read_text())
    index = json.loads(safe(root, 'index.json').read_text())
    for doc in index['documents']:
        need(doc['path'] in manifest['files'], 'Unbound research document')
    packages = catalog['packages']
    need(len({p['id'] for p in packages}) == len(packages), 'Duplicate package id')
    for p in packages:
        for field in ('works', 'core_relations', 'methods'):
            need(len({x['id'] for x in p[field]}) == len(p[field]), 'Duplicate package-scoped id')
        works = {w['id'] for w in p['works']}
        relations = {r['id'] for r in p['core_relations']}
        for r in p['core_relations']:
            need(set(r['work_ids']) <= works, 'Unknown work in relation')
        for m in p['methods']:
            need(set(m['relation_ids']) <= relations, 'Unknown relation in method')
    return manifest, catalog, index


def package(catalog, identifier):
    matches = [p for p in catalog['packages'] if p['id'] == identifier]
    need(len(matches) == 1, 'Unknown knowledge package: ' + identifier)
    return matches[0]


def search(root, query, limit=12):
    manifest, catalog, index = load(root)
    terms = [x.casefold() for x in re.split(r'\s+', query.strip()) if x]
    need(terms, 'Supply a search term or phrase')
    results = []
    for p in catalog['packages']:
        body = json.dumps(p, ensure_ascii=False).casefold()
        score = sum(body.count(t) for t in terms)
        if score:
            results.append({'kind': 'direction', 'id': p['id'], 'title': p['label'], 'author': p['author'],
                            'score': score, 'path': manifest['catalog'], 'status': p['status']})
    for d in index['documents']:
        if d['kind'] == 'style-library':
            continue  # Directions are ranked individually, not as a huge JSON corpus.
        body = safe(root, d['path']).read_text().casefold()
        score = sum(body.count(t) for t in terms)
        if score:
            results.append({**d, 'score': score})
    # Lexical retrieval only; ranking does not decide whether a method fits a photo.
    return sorted(results, key=lambda r: (-r['score'], r['id']))[:limit]


def template(root, identifier, source_id):
    _, catalog, _ = load(root)
    p = package(catalog, identifier)
    return {'schema': 'darkroom-knowledge-plan/1', 'source_sha256': source_id,
            'library_sha256': digest(safe(root, 'manifest.json')), 'package_id': identifier,
            'mode': 'text_only_hypothesis', 'reference_limit': '',
            'source_observation': '', 'intent': '', 'documents': [],
            'fit': {key: [{'condition': x, 'matches': None, 'observation': ''} for x in p['fit'][key]]
                    for key in ('required', 'incompatible')},
            'references': [{'work_id': w['id'], 'status': 'unavailable', 'observation': ''}
                           for w in p['works'] if w['role'] in ('primary', 'boundary')],
            'relations': [{'id': r['id'], 'decision': '', 'observation': '', 'target': '',
                           'failure_signal': r['failure_signal'], 'method_ids': []}
                          for r in p['core_relations']], 'operations': []}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def changed_operations(parameters, mask, geometry, registry):
    fields = {o['field']: o['operation_id'] for o in registry['operations'] if o.get('field')}
    need(set(parameters) <= set(fields), 'Unknown parameter in knowledge receipt')
    result = {fields[k] for k, v in parameters.items() if k not in NEUTRAL or NEUTRAL[k] != v}
    if mask:
        types = {'brush': 'acr.brush_mask', 'linear_gradient': 'acr.linear_gradient_mask',
                 'radial_gradient': 'acr.radial_gradient_mask', 'luminance_range': 'acr.luminance_range_mask'}
        for g in mask['groups']:
            for m in g['masks']:
                need(m['type'] in types, 'Unsupported manual mask')
                result.add(types[m['type']])
    if geometry:
        result.add('composition.native_crop')
    return sorted(result)


def validate_receipt(workspace, receipt, source_id, card, geometry):
    """Called by the actual compiler, not merely by the friendly command wrapper."""
    root = Path(workspace)
    need(receipt.get('source_sha256') == source_id, 'Receipt source mismatch')
    parameters = {}
    for rule in card['parameter_rules']:
        value = rule['value_spec']
        need(value['kind'] == 'absolute' and rule['field'] not in parameters, 'Public card requires unique absolute rules')
        scalar = value['value']
        parameters[rule['field']] = scalar['points'] if scalar['type'] == 'curve' else scalar['value']
    need(parameters == receipt.get('parameters') and card.get('mask_recipe') == receipt.get('mask_recipe')
         and geometry == receipt.get('geometry'), 'Knowledge reasoning and executed card differ')
    need(set(NEUTRAL) <= set(parameters), 'Neutral defaults must be explicit')
    if receipt.get('role') == 'probe':
        need(source_id == SYNTHETIC_SHA256, 'Probe mode only accepts the bundled generated fixture')
        need(receipt.get('knowledge_plan') is None, 'Probe does not establish knowledge transfer')
        return []
    if receipt.get('role') == 'baseline':
        need(parameters == NEUTRAL and not geometry and not card.get('mask_recipe') and receipt.get('knowledge_plan') is None,
             'Baseline cannot bypass knowledge planning for an edit')
        return []
    need(receipt.get('role') == 'edit', 'Unknown public plan role')
    registry = json.loads((root / 'registries/adobe-operation-registry-v1.json').read_text())
    ops = changed_operations(parameters, card.get('mask_recipe'), geometry, registry)
    result = validate_plan(root / 'knowledge/library', receipt.get('knowledge_plan'), source_id, ops)
    need(result == receipt.get('knowledge_result'), 'Knowledge receipt changed')
    # Bind the whole immutable library, including atlas and source notes, to replay.
    manifest, _, _ = load(root / 'knowledge/library')
    return ['knowledge/library/' + name for name in ['manifest.json', *manifest['files']]]


def validate_plan(root, plan, source_id, operation_ids):
    manifest, catalog, index = load(root)
    need(isinstance(plan, dict) and plan.get('schema') == 'darkroom-knowledge-plan/1', 'Knowledge plan required')
    need(plan.get('source_sha256') == source_id, 'Knowledge plan belongs to another source')
    need(plan.get('library_sha256') == digest(safe(root, 'manifest.json')), 'Knowledge plan uses another library')
    p = package(catalog, plan.get('package_id', ''))
    need(plan.get('mode') in ('visual_reference', 'text_only_hypothesis'), 'Unknown reference mode')
    for key in ('source_observation', 'intent'):
        need(nonempty(plan.get(key)), 'Missing photo-specific ' + key)
    methods = {m['id']: m for m in p['methods']}
    relations = {r['id']: r for r in p['core_relations']}
    for key, expected in (('required', True), ('incompatible', False)):
        rows = plan.get('fit', {}).get(key, [])
        need([r.get('condition') for r in rows] == p['fit'][key], 'Fit checklist differs from library')
        need(all(r.get('matches') is expected and nonempty(r.get('observation')) for r in rows),
             'Source does not establish compatibility with this direction')
    rows = plan.get('relations', [])
    need(len(rows) == len(relations) and {r['id'] for r in rows} == set(relations), 'Every core relation needs a decision')
    for r in rows:
        need(r.get('decision') in ('preserve', 'adjust', 'not_applicable'), 'Invalid relation decision')
        need(all(nonempty(r.get(k)) for k in ('observation', 'target', 'failure_signal')), 'Incomplete relation reasoning')
        ids = r.get('method_ids', [])
        need(isinstance(ids, list) and set(ids) <= set(methods), 'Unknown library method')
        need(all(r['id'] in methods[mid]['relation_ids'] for mid in ids), 'Method is not linked to this relation')
        if r['decision'] == 'adjust':
            need(ids, 'Adjusted relation needs a method')
    works = {w['id']: w for w in p['works']}
    refs = plan.get('references', [])
    need(len({r.get('work_id') for r in refs}) == len(refs), 'Duplicate reference')
    for r in refs:
        need(r.get('work_id') in works and r.get('status') in ('viewed', 'unavailable'), 'Unknown reference/status')
        need(nonempty(r.get('observation')), 'Record actual viewing or why reference unavailable')
    roles = [works[r['work_id']]['role'] for r in refs]
    need(roles.count('primary') >= 2 and 'boundary' in roles, 'Record access to two primary and one boundary reference')
    if plan['mode'] == 'visual_reference':
        viewed = [works[r['work_id']] for r in refs if r['status'] == 'viewed']
        need(sum(w['role'] == 'primary' for w in viewed) >= 2 and any(w['role'] == 'boundary' for w in viewed),
             'Visual comparison needs two primary works and one boundary work')
    else:
        need(nonempty(plan.get('reference_limit')), 'Text-only mode must disclose unavailable visual evidence')
    documents = {d['id']: d for d in index['documents']}
    need(isinstance(plan.get('documents'), list), 'Documents must list the records actually read')
    for identifier in plan['documents']:
        need(identifier in documents, 'Unknown research document')
    ops = plan.get('operations', [])
    need(len({o.get('operation_id') for o in ops}) == len(ops), 'Duplicate operation binding')
    need({o.get('operation_id') for o in ops} == set(operation_ids), 'Knowledge plan must bind exact changed operations')
    for op in ops:
        need(nonempty(op.get('rationale')), 'Operation needs photo-specific rationale')
        mids, rids = op.get('method_ids', []), op.get('relation_ids', [])
        need(set(mids) <= set(methods) and rids and set(rids) <= set(relations), 'Unknown operation relationship')
        need(all(next(r for r in rows if r['id'] == rid)['decision'] == 'adjust' for rid in rids),
             'An executed change cannot be labelled preserved/not applicable')
        if op.get('basis') == 'library_method':
            need(mids, 'Library operation needs its method')
            for mid in mids:
                m = methods[mid]
                crop = op['operation_id'] == 'composition.native_crop' and m.get('strategy') == 'composition_decision'
                need(op['operation_id'] in m['operation_ids'] or crop, 'Operation is not supported by cited method')
                need(set(rids) & set(m['relation_ids']), 'Method does not support cited relation')
        else:
            need(op.get('basis') == 'image_specific' and not mids, 'Separate personal parameter decisions from library attribution')
    files = {manifest['catalog'], 'manifest.json', 'index.json'}
    files.update(documents[i]['path'] for i in plan['documents'])
    return {'package_id': p['id'], 'label': p['label'], 'mode': plan['mode'],
            'library_sha256': plan['library_sha256'], 'quality_verified': False,
            'documents': plan['documents'], 'files': sorted(files)}
