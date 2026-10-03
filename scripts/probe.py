#!/usr/bin/env python3
"""Real Adobe test of self-generated pixels only; explicit invocation."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import struct
import sys

import darkroom
from generate_fixture import generate


def tiff_mean(path):
    data = Path(path).read_bytes()
    order = '<' if data[:2] == b'II' else '>'
    offset = struct.unpack_from(order + 'I', data, 4)[0]
    count = struct.unpack_from(order + 'H', data, offset)[0]
    tags = {}
    for n in range(count):
        tag, typ, size = struct.unpack_from(order + 'HHI', data, offset + 2 + n * 12)
        value_at = offset + 2 + n * 12 + 8
        width = {3: 2, 4: 4}.get(typ)
        if width and size <= 3:
            position = value_at if width * size <= 4 else struct.unpack_from(order + 'I', data, value_at)[0]
            tags[tag] = struct.unpack_from(order + ({3: 'H', 4: 'I'}[typ] * size), data, position)
    darkroom.require(tags.get(258) == (16, 16, 16), 'Expected 16-bit RGB TIFF')
    darkroom.require(len(tags[273]) == len(tags[279]) == 1, 'Expected a single TIFF strip')
    values = array.array('H', data[tags[273][0]:tags[273][0] + tags[279][0]])
    if (order == '<') != (sys.byteorder == 'little'):
        values.byteswap()
    return sum(values) / len(values)


def probe(directory, app=None):
    root = Path(directory).expanduser().absolute()
    darkroom.require(root.resolve() == root and not root.exists(), 'Choose a new probe directory without symlinks')
    environment = darkroom.doctor(app)
    darkroom.require(environment['ready'], environment.get('error', 'Environment unavailable'))
    root.mkdir(parents=True)
    source = root / 'synthetic.dng'; generate(source)
    before = darkroom.sha(source)
    work = root / 'workspace'; darkroom.init_workspace(str(work))
    receipt = darkroom.ingest(str(work), str(source), 'Explicitly invoked self-generated fixture probe; no user photograph.')
    results = []
    mask = {'schema_version': 'mask_graph/v1', 'coordinate_space': 'normalized_upright',
            'groups': [{'id': 'probe.light', 'name': 'Synthetic local light', 'operation_order': 0,
                        'local_adjustments': {'exposure2012': '0.5'},
                        'masks': [{'id': 'probe.brush', 'type': 'brush', 'composition': 'add',
                                   'dabs': [{'x': '0.5', 'y': '0.5', 'radius': '0.15', 'flow': '1', 'feather': '0.5'}]}]}]}
    mask['graph_sha256'] = hashlib.sha256(json.dumps(mask, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    mask_path = root / 'synthetic-mask.json'; darkroom.save(mask_path, mask)
    for label, recipe, mask_file in (('neutral', 'neutral.json', None), ('exposure', 'exposure-probe.json', None),
                                    ('manual-brush', 'neutral.json', mask_path)):
        result = darkroom.prepare(str(work), receipt['source_id'], str(darkroom.PACKAGE / 'examples' / recipe), 'Synthetic transport probe: ' + label, role='probe', mask_file=mask_file)
        rendered = darkroom.render(str(work), result['plan'], app)
        folder = work / rendered['output']
        manifest = json.loads((folder / 'PHOTO-frame.manifest.json').read_text())
        results.append({'recipe': label, 'render_pass': manifest['render_pass'],
                        'replay': manifest['gates']['G2_replay_deterministic'],
                        'pixels': manifest['master_pixel_strip_sha256'],
                        'mean_rgb16': tiff_mean(folder / 'PHOTO-frame.tif')})
    # A separate test fixture workspace exercises DNG geometry without granting
    # additional attempts to any user's photo or resetting a photographic failure.
    geometry = {'schemaVersion': 1, 'kind': 'acr_native_crop', 'sourceDimensions': [512, 384],
                'rect': [64, 48, 448, 336], 'angleDegrees': 0}
    geometry_path = root / 'synthetic-geometry.json'; darkroom.save(geometry_path, geometry)
    crop_work = root / 'geometry-workspace'; darkroom.init_workspace(str(crop_work))
    crop_source = darkroom.ingest(str(crop_work), str(source), 'Explicit synthetic geometry probe; not a user photo.')
    crop_plan = darkroom.prepare(str(crop_work), crop_source['source_id'], str(darkroom.PACKAGE / 'examples/neutral.json'),
                                'Synthetic DNG crop transport', role='probe', geometry_file=geometry_path)
    crop_render = darkroom.render(str(crop_work), crop_plan['plan'], app)
    crop_manifest = json.loads((crop_work / crop_render['output'] / 'PHOTO-frame.manifest.json').read_text())
    geometry_result = {'render_pass': crop_manifest['render_pass'],
                       'replay': crop_manifest['gates']['G2_replay_deterministic'],
                       'geometry': crop_manifest.get('acr_geometry')}
    unchanged = before == darkroom.sha(source)
    changed = results[0]['pixels'] != results[1]['pixels']
    brighter = results[1]['mean_rgb16'] > results[0]['mean_rgb16']
    environment['automation_permission'] = 'verified_in_this_probe'
    result = {'fixture': 'self-generated-linear-dng', 'source_unchanged': unchanged,
              'source_directory_has_no_sidecar': not source.with_suffix('.xmp').exists(),
              'pixels_changed': changed, 'exposure_increased_brightness': brighter,
              'manual_brush_changed_pixels': results[2]['pixels'] != results[0]['pixels'],
              'manual_brush_increased_brightness': results[2]['mean_rgb16'] > results[0]['mean_rgb16'],
              'native_geometry': geometry_result,
              'renders': results, 'environment': environment,
              'second_machine_verified': False, 'photographic_quality_verified': False}
    result['pass'] = unchanged and changed and brighter and result['source_directory_has_no_sidecar'] and all(r['render_pass'] and r['replay'] for r in results) and result['manual_brush_changed_pixels'] and result['manual_brush_increased_brightness'] and geometry_result['render_pass'] and geometry_result['replay']
    darkroom.save(root / 'probe-report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--photoshop-app')
    args = parser.parse_args()
    result = probe(args.directory, args.photoshop_app)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['pass'] else 1)
