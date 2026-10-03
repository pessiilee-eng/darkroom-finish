#!/usr/bin/env python3
"""Real Adobe test of self-generated pixels only; explicit invocation."""
import argparse
import array
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
    for recipe in ('neutral.json', 'exposure-probe.json'):
        result = darkroom.prepare(str(work), receipt['source_id'], str(darkroom.PACKAGE / 'examples' / recipe), 'Synthetic transport and exposure probe: ' + recipe)
        rendered = darkroom.render(str(work), result['plan'], app)
        folder = work / rendered['output']
        manifest = json.loads((folder / 'PHOTO-frame.manifest.json').read_text())
        results.append({'recipe': recipe, 'render_pass': manifest['render_pass'],
                        'replay': manifest['gates']['G2_replay_deterministic'],
                        'pixels': manifest['master_pixel_strip_sha256'],
                        'mean_rgb16': tiff_mean(folder / 'PHOTO-frame.tif')})
    unchanged = before == darkroom.sha(source)
    changed = results[0]['pixels'] != results[1]['pixels']
    brighter = results[1]['mean_rgb16'] > results[0]['mean_rgb16']
    environment['automation_permission'] = 'verified_in_this_probe'
    result = {'fixture': 'self-generated-linear-dng', 'source_unchanged': unchanged,
              'source_directory_has_no_sidecar': not source.with_suffix('.xmp').exists(),
              'pixels_changed': changed, 'exposure_increased_brightness': brighter,
              'renders': results, 'environment': environment,
              'second_machine_verified': False, 'photographic_quality_verified': False}
    result['pass'] = unchanged and changed and brighter and result['source_directory_has_no_sidecar'] and all(r['render_pass'] and r['replay'] for r in results)
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
