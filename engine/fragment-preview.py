"""Recover indexed camera previews from current source bytes, without historical allocation."""
import importlib
import io
import math
import os
import warnings
from PIL import Image

MAX_STARTS = 32
MAX_END_CHECKS = 1000000
MAX_JOINS = 2048
MAX_PREVIEW = 4 * 1024 * 1024


def describe(fd, start, total):
    size = min(65536, total - start)
    raw = os.pread(fd, size, start)
    if len(raw) != size:
        raise OSError('Short preview header read')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(io.BytesIO(raw)) as photo:
                if photo.format in ('JPEG', 'MPO') and 256 < max(photo.size) <= 2048:
                    return {'offset': start, 'dimensions': list(photo.size)}
    except (OSError, ValueError, SyntaxError, Warning):
        pass
    return None


def reconstruct(fd, total, candidate, starts, cluster, heap, verify):
    carve = importlib.import_module('carve-photos')
    scan = importlib.import_module('scan-images')
    length = candidate['preview_bytes']
    thumb = candidate['thumbnail']
    if thumb is None or not 0 < length <= MAX_PREVIEW:
        return None, 'missing_thumbnail_or_preview_budget'
    aligned = [row for row in starts if row['offset'] >= heap
               and (row['offset'] - candidate['offset'] - candidate['preview_logical']) % cluster == 0]
    if not aligned or len(aligned) > MAX_STARTS:
        return None, 'missing_preview_header_or_search_budget'
    # Search the current allocation heap, including regions with no intact photos.
    within = (aligned[0]['offset'] - heap + length) % cluster
    end_count = max(0, (total - heap - within) // cluster + 1)
    if end_count > MAX_END_CHECKS:
        return None, 'preview_endpoint_search_budget'
    ends = []
    for index, end in enumerate(range(heap + within, total + 1, cluster)):
        if index % 256 == 0:
            verify()
        if end < heap + 2:
            continue
        marker = os.pread(fd, 2, end - 2)
        if len(marker) != 2:
            raise OSError('Short preview endpoint read')
        if marker == b'\xff\xd9':
            ends.append(end)
            if len(ends) > MAX_JOINS:
                return None, 'preview_endpoint_search_budget'
    accepted = None
    attempts = 0
    for row in aligned:
        start = row['offset']
        first = cluster - (start - heap) % cluster
        for cut in range(first, length, cluster):
            verify()
            prefix = os.pread(fd, cut, start)
            if len(prefix) != cut:
                raise OSError('Short preview prefix read')
            remaining = length - cut
            for end in ends:
                verify()
                suffix = end - remaining
                if suffix < heap or (suffix < start + cut and end > start):
                    continue
                attempts += 1
                if attempts > MAX_JOINS:
                    return None, 'preview_join_search_budget'
                tail = os.pread(fd, remaining, suffix)
                if len(tail) != remaining:
                    raise OSError('Short preview tail read')
                raw = prefix + tail
                try:
                    n, dims = carve.jpeg_extent(None, 0, length, lambda _, count, pos: raw[pos:pos+count])
                    if n != length or dims != row['dimensions']:
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter('error')
                        with Image.open(io.BytesIO(raw)) as photo:
                            photo.load()
                            difference = scan.thumbnail_difference(photo, thumb)
                    if difference > 5:
                        continue
                except (OSError, ValueError, SyntaxError, Warning):
                    continue
                if accepted is not None:
                    return None, 'ambiguous_preview_joins'
                accepted = {'data': raw, 'offset': start, 'bytes': length, 'dimensions': dims,
                            'thumbnail_difference': difference, 'source_extents': [
                                {'offset': start, 'bytes': cut}, {'offset': suffix, 'bytes': remaining}]}
    return accepted, 'reconstructed_preview' if accepted else 'no_valid_preview_join'
