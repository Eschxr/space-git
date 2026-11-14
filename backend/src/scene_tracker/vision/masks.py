"""COCO compressed RLE stored as JSON-safe text, validated before native decoding."""

import numpy as np
from pycocotools import mask as coco

from scene_tracker.domain.contracts import Mask


def encode_mask(binary) -> Mask:
    array = np.asarray(binary)
    if array.ndim != 2 or not np.isin(array, [0, 1]).all():
        raise ValueError("expected binary 2D mask")
    packed = coco.encode(np.asfortranarray(array, dtype=np.uint8))
    return Mask(size=tuple(packed["size"]), counts=packed["counts"].decode("ascii"))


def decode_mask(rle: Mask):
    # Validate the COCO variable-length signed-delta counts in Python before C code.
    counts = []
    position = 0
    while position < len(rle.counts):
        value = 0
        shift = 0
        while True:
            if position >= len(rle.counts) or shift > 60:
                raise ValueError("invalid compressed RLE")
            code = ord(rle.counts[position]) - 48
            position += 1
            if not 0 <= code <= 63:
                raise ValueError("invalid RLE character")
            value |= (code & 31) << shift
            shift += 5
            if not code & 32:
                if code & 16:
                    value |= -1 << shift
                break
        if len(counts) > 2:
            value += counts[-2]
        if value < 0:
            raise ValueError("negative RLE run")
        counts.append(value)
    if sum(counts) != rle.size[0] * rle.size[1]:
        raise ValueError("RLE pixel count mismatch")
    return coco.decode({"size": list(rle.size), "counts": rle.counts.encode("ascii")})
