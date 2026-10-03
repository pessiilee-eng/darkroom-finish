import hashlib


import json


import plistlib


import shutil


import struct


import subprocess


import sys


from datetime import datetime, timezone


from pathlib import Path


def tiff_strip_sha256(path: Path) -> str:
    """Hash only the image strip (pixel data), excluding metadata like
    DateTime/XMP that Photoshop rewrites on every save."""
    d = path.read_bytes()
    bo = ">" if d[:2] == b"MM" else "<"
    ifd_off = struct.unpack(bo + "I", d[4:8])[0]
    n = struct.unpack(bo + "H", d[ifd_off:ifd_off + 2])[0]
    tags = {}
    for i in range(n):
        e = ifd_off + 2 + i * 12
        tag, _typ, cnt = struct.unpack(bo + "HHI", d[e:e + 8])
        tags[tag] = (cnt, struct.unpack(bo + "I", d[e + 8:e + 12])[0])
    strips_cnt, strips_val = tags[0x0111]
    counts_cnt, counts_val = tags[0x0117]
    if strips_cnt != 1 or counts_cnt != 1:
        raise ValueError(f"expected single-strip TIFF, got {strips_cnt} strips")
    return hashlib.sha256(d[strips_val:strips_val + counts_val]).hexdigest()

