"""Native ACR crop intent; no pixel resampling and no Adobe verification claims.

Coordinates are on the full upright RAW canvas after rotating image content
clockwise about that canvas's centre. CRS uses source-space diagonal endpoints
and a counterclockwise-positive angle; TIFF Orientation is resolved from RAW.
"""
from decimal import Decimal, InvalidOperation
import math
from pathlib import Path
import struct

CROP_KEYS = frozenset({'HasCrop', 'CropLeft', 'CropTop', 'CropRight', 'CropBottom', 'CropAngle'})


def validate_geometry_plan(plan):
    keys = {'schemaVersion', 'kind', 'sourceDimensions', 'rect', 'angleDegrees'}
    if not isinstance(plan, dict) or set(plan) != keys or type(plan['schemaVersion']) is not int or plan['schemaVersion'] != 1 or plan['kind'] != 'acr_native_crop':
        raise ValueError('invalid native ACR geometry plan')
    dims, rect, angle = plan['sourceDimensions'], plan['rect'], plan['angleDegrees']
    if not isinstance(dims, list) or len(dims) != 2 or any(type(x) is not int or x <= 0 for x in dims):
        raise ValueError('native crop requires positive upright source dimensions')
    if not isinstance(rect, list) or len(rect) != 4 or any(type(x) not in (int, float) or not math.isfinite(x) for x in rect):
        raise ValueError('native crop requires four finite boundary coordinates')
    left, top, right, bottom = rect
    width, height = dims
    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
        raise ValueError('native crop rectangle outside source')
    if type(angle) not in (int, float) or not math.isfinite(angle) or not -3 <= angle <= 3:
        raise ValueError('native crop angle must be finite and within +/-3 degrees')
    return plan


def decimal_text(value):
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def geometry_params(plan, orientation):
    validate_geometry_plan(plan)
    if orientation not in (1, 6, 8) or type(orientation) is not int:
        raise ValueError('native geometry currently supports RAW Orientation 1, 6 or 8 only')
    width, height = (Decimal(str(x)) for x in plan['sourceDimensions'])
    left, top, right, bottom = (Decimal(str(x)) for x in plan['rect'])
    # CRS boundaries describe the source-space diagonal, not a bounding box
    # around the four rotated corners. Preserve fractional FOV throughout.
    angle = Decimal(str(plan['angleDegrees']))
    radians = math.radians(float(angle))
    cosine, sine = Decimal(str(math.cos(radians))), Decimal(str(math.sin(radians)))
    cx, cy = width / 2, height / 2
    corners = [(cosine * (x - cx) + sine * (y - cy) + cx,
                -sine * (x - cx) + cosine * (y - cy) + cy)
               for x, y in ((left, top), (right, top), (right, bottom), (left, bottom))]
    if any(not (0 <= x <= width and 0 <= y <= height) for x, y in corners):
        raise ValueError('native rotated crop crosses source coverage')
    if orientation == 1:
        (l, t), (r, b) = corners[0], corners[2]
    elif orientation == 6:
        (x1, y1), (x2, y2) = corners[1], corners[3]
        l, t, r, b = y1, width - x1, y2, width - x2
        width, height = height, width
    else:
        (x1, y1), (x2, y2) = corners[3], corners[1]
        l, t, r, b = height - y1, x1, height - y2, x2
        width, height = height, width
    params = {'HasCrop': 'True', 'CropLeft': decimal_text(l / width), 'CropTop': decimal_text(t / height),
              'CropRight': decimal_text(r / width), 'CropBottom': decimal_text(b / height),
              'CropAngle': decimal_text(-angle if angle else Decimal(0))}
    validate_crop_parameters(params)
    return params


def validate_crop_parameters(params):
    present = CROP_KEYS.intersection(params)
    if not present:
        return
    if present != CROP_KEYS or params.get('HasCrop') != 'True':
        raise ValueError('native ACR crop requires all six fields with HasCrop=True')
    if any(not isinstance(params[key], str) for key in CROP_KEYS):
        raise ValueError('native ACR crop values must use decimal strings')
    try:
        values = {key: Decimal(params[key]) for key in CROP_KEYS - {'HasCrop'}}
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('native ACR crop values must be finite decimals') from None
    if not all(value.is_finite() for value in values.values()):
        raise ValueError('native ACR crop values must be finite decimals')
    if not (0 <= values['CropLeft'] < values['CropRight'] <= 1 and
            0 <= values['CropTop'] < values['CropBottom'] <= 1 and -3 <= values['CropAngle'] <= 3):
        raise ValueError('invalid grouped native ACR crop boundaries or angle')


def merge_geometry(params, plan, orientation=None):
    """The separately frozen plan is the only production geometry authority."""
    present = CROP_KEYS.intersection(params)
    if plan is None:
        if present:
            raise ValueError('native crop fields require --acr-geometry-plan')
        return dict(params)
    crop = geometry_params(plan, orientation)
    if present:
        validate_crop_parameters(params)
    if present and (present != CROP_KEYS or any(Decimal(params[key]) != Decimal(crop[key])
                    for key in present - {'HasCrop'}) or params['HasCrop'] != crop['HasCrop']):
        raise ValueError('card native crop conflicts with frozen geometry plan')
    return {**params, **crop}


def tiff_dimensions(path):
    """Read dimensions from a classic TIFF header, without loading photo pixels."""
    with Path(path).open('rb') as handle:
        header = handle.read(8)
        if len(header) != 8 or header[:2] not in (b'II', b'MM'):
            raise ValueError('native geometry output is not TIFF')
        order = '<' if header[:2] == b'II' else '>'
        magic, offset = struct.unpack(order + 'HI', header[2:])
        if magic != 42:
            raise ValueError('native geometry needs classic TIFF dimensions')
        handle.seek(offset)
        count = struct.unpack(order + 'H', handle.read(2))[0]
        dimensions = {}
        for _ in range(count):
            entry = handle.read(12)
            tag, kind, count = struct.unpack(order + 'HHI', entry[:8])
            if tag in (256, 257):
                if count != 1 or kind not in (3, 4):
                    raise ValueError('unexpected TIFF dimension encoding')
                dimensions[tag] = struct.unpack(order + ('H' if kind == 3 else 'I'), entry[8:10] if kind == 3 else entry[8:])[0]
        if set(dimensions) != {256, 257}:
            raise ValueError('TIFF dimensions missing')
        return [dimensions[256], dimensions[257]]


def read_raw_orientation(path):
    """Read only the DNG's primary TIFF metadata; never infer upright from shape."""
    if Path(path).suffix.lower() != '.dng':
        raise ValueError('native ACR geometry is currently admitted for DNG only')
    with Path(path).open('rb') as handle:
        header = handle.read(8)
        if len(header) != 8 or header[:2] not in (b'II', b'MM'):
            raise ValueError('DNG TIFF header missing')
        order = '<' if header[:2] == b'II' else '>'
        magic, offset = struct.unpack(order + 'HI', header[2:])
        if magic != 42:
            raise ValueError('native geometry requires classic TIFF DNG metadata')
        handle.seek(offset)
        count = struct.unpack(order + 'H', handle.read(2))[0]
        if count > 4096:
            raise ValueError('DNG metadata directory is unexpectedly large')
        found = []
        for _ in range(count):
            entry = handle.read(12)
            tag, kind, n = struct.unpack(order + 'HHI', entry[:8])
            if tag == 274:
                if kind != 3 or n != 1:
                    raise ValueError('DNG Orientation metadata is malformed')
                found.append(struct.unpack(order + 'H', entry[8:10])[0])
        if len(found) != 1 or found[0] not in (1, 6, 8):
            raise ValueError('DNG must explicitly declare supported Orientation 1, 6 or 8')
        return found[0]


def geometry_evidence(plan, master, replay, orientation):
    validate_geometry_plan(plan)
    actual, repeated = tiff_dimensions(master), tiff_dimensions(replay)
    left, top, right, bottom = (Decimal(str(x)) for x in plan['rect'])
    spans = [right - left, bottom - top]
    expected = [round(span) for span in spans]
    delta = [a - e for a, e in zip(actual, expected)]
    return {'plan': plan, 'source_orientation': orientation, 'plan_angle_semantics': 'image_content_clockwise_positive',
            'plan_coordinates': 'same_size_upright_canvas_rotated_about_full_canvas_center',
            'native_parameters': geometry_params(plan, orientation), 'expected_dimensions': expected,
            'requested_native_spans': [decimal_text(span) for span in spans],
            'requested_aspect_ratio': decimal_text(spans[0] / spans[1]),
            'actual_aspect_ratio': decimal_text(Decimal(actual[0]) / Decimal(actual[1])),
            'actual_dimensions': actual, 'replay_dimensions': repeated, 'dimension_delta_pixels': delta,
            'dimension_gate_passed': actual == repeated and all(abs(x) <= 1 for x in delta),
            'dimension_tolerance_pixels': 1, 'post_render_resize': False, 'post_render_crop': False,
            'exact_ratio_preserved': Decimal(actual[0]) * spans[1] == Decimal(actual[1]) * spans[0],
            'native_orientation_angle_and_framing': 'REQUIRES_VISUAL_VERIFICATION',
            'scene_content_generated': False}
