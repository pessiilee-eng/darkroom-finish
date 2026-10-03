#!/usr/bin/env python3
"""Make a local sRGB JPEG <=1600 px, retaining only a standard sRGB ICC.

This helper does not upload. Obtain permission before sending the result to AI.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageCms, ImageOps


def preview(source, target):
    source, target = Path(source), Path(target)
    if target.exists() or source.resolve() == target.resolve():
        raise ValueError('Output must be a new file, never the source')
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
    with Image.open(source) as image:
        if image.format not in ('JPEG', 'PNG'):
            raise ValueError('Use a rendered JPEG/PNG, not a RAW or full-size TIFF')
        icc = image.info.get('icc_profile')
        if not icc:
            raise ValueError('Input must have an embedded color profile; do not guess sRGB')
        rgb = ImageOps.exif_transpose(image).convert('RGB')
        rgb = ImageCms.profileToProfile(rgb, ImageCms.ImageCmsProfile(io.BytesIO(icc)), srgb, outputMode='RGB')
        rgb.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        clean = Image.new('RGB', rgb.size)
        clean.paste(rgb)
        if max(pair[1] for pair in clean.getextrema()) == 0:
            raise ValueError('All-black output requires inspection')
        buffer = io.BytesIO()
        clean.save(buffer, format='JPEG', quality=92, subsampling=0, icc_profile=srgb.tobytes())
    with Image.open(io.BytesIO(buffer.getvalue())) as check:
        check.load()
        if check.getexif() or 'xmp' in check.info or 'comment' in check.info or check.mode != 'RGB' or max(check.size) > 1600:
            raise ValueError('Metadata or output contract failure')
        dimensions = list(check.size)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError('Source changed during preview creation')
    with target.open('xb') as handle:
        handle.write(buffer.getvalue())
    return {'dimensions': dimensions, 'sha256': hashlib.sha256(buffer.getvalue()).hexdigest(),
            'metadata': 'standard sRGB ICC and JPEG structure only', 'uploaded': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(preview(args.input, args.output)))
