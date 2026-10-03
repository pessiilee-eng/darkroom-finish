#!/usr/bin/env python3
"""Create an original synthetic linear DNG, with no photograph or EXIF/GPS.

Used to test Adobe transport, not camera support or artistic quality.
"""
import argparse
from pathlib import Path
import struct


def generate(path):
    width, height = 512, 384
    tags = []
    def tag(key, typ, count, value):
        tags.append((key, typ, count, value))
    def short(key, *values):
        tag(key, 3, len(values), struct.pack('<' + 'H' * len(values), *values))
    def long(key, *values):
        tag(key, 4, len(values), struct.pack('<' + 'I' * len(values), *values))
    def ascii_tag(key, value):
        data = value.encode('ascii') + b'\0'; tag(key, 2, len(data), data)
    long(254, 0); long(256, width); long(257, height); short(258, 16, 16, 16)
    short(259, 1); short(262, 34892); short(274, 1)
    short(277, 3); long(278, height); long(279, width * height * 6)
    short(284, 1); long(273, 0)
    tag(50706, 1, 4, bytes([1, 4, 0, 0])); tag(50707, 1, 4, bytes([1, 1, 0, 0]))
    ascii_tag(50708, 'Darkroom Synthetic Linear'); ascii_tag(271, 'Synthetic'); ascii_tag(272, 'Linear RGB fixture')
    long(50714, 0); long(50717, 65535); long(50719, 0, 0); long(50720, width, height)
    # Simple invertible camera-to-XYZ matrix and white reference.
    matrix = [4124, 3576, 1805, 2126, 7152, 722, 193, 1192, 9505]
    tag(50721, 10, 9, b''.join(struct.pack('<ii', x, 10000) for x in matrix))
    tag(50728, 5, 3, struct.pack('<IIIIII', 1, 1, 1, 1, 1, 1))
    short(50778, 21)
    tags.sort()
    offset = 8 + 2 + 12 * len(tags) + 4
    payload = bytearray(); entries = []
    for key, typ, count, data in tags:
        if len(data) > 4:
            if (offset + len(payload)) % 2:
                payload += b'\0'
            pointer = offset + len(payload)
            payload += data
            data = struct.pack('<I', pointer)
        entries.append([key, typ, count, data.ljust(4, b'\0')])
    pixel_offset = offset + len(payload)
    for entry in entries:
        if entry[0] == 273:
            entry[3] = struct.pack('<I', pixel_offset)
    data = bytearray(b'II' + struct.pack('<HI', 42, 8) + struct.pack('<H', len(tags)))
    for key, typ, count, encoded in entries:
        data += struct.pack('<HHI', key, typ, count) + encoded
    data += struct.pack('<I', 0) + payload
    for y in range(height):
        for x in range(width):
            level = 3000 + int(26000 * x / (width - 1))
            factors = ((1, 0.7, 0.5), (0.6, 1, 0.7), (0.5, 0.7, 1))[y // (height // 3)]
            data += struct.pack('<HHH', *(int(level * f) for f in factors))
    with Path(path).open('xb') as handle:
        handle.write(data)
    return len(data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(generate(args.output))
