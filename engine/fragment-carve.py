"""Bounded original-byte JPEG reconstruction using a camera MPF preview as a tail anchor."""
import collections
import importlib
import io
import json
import math
import os
import warnings
from PIL import Image, ImageChops, ImageStat

scan = importlib.import_module('scan-images')
metadata = importlib.import_module('assemble-metadata')
MAX_HEADER = 1024 * 1024
MAX_BOUNDARIES = 1024
# shortcut: two contiguous extents only; expand after a verified multi-extent recovery.


def header(fd, start, total):
    length = min(MAX_HEADER, total - start)
    raw = os.pread(fd, length, start)
    if len(raw) != length:
        raise OSError('Short fragment header read')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(io.BytesIO(raw)) as photo:
                exif = photo.getexif()
                entries = getattr(photo, 'mpinfo', {}).get(45058, [])
                base = metadata.mpf_base(None, raw)
                if (max(photo.size) <= 2048 or photo.width * photo.height > 64_000_000
                        or not exif.get(271) or not exif.get(272) or len(entries) != 2 or base is None):
                    return None
                primary, child = entries
                length = primary['Size']
                logical = base + child['DataOffset']
                if (primary['DataOffset'] != 0 or not 0 < length <= 128 * 1024 * 1024
                        or not length <= logical < 128 * 1024 * 1024
                        or not 0 < child['Size'] <= 128 * 1024 * 1024
                        or not child['Attribute']['DependentChildImageFlag']
                        or 'Thumbnail' not in child['Attribute']['MPType']):
                    return None
                return {'offset': start, 'bytes': length, 'dimensions': list(photo.size),
                        'preview_logical': logical, 'preview_bytes': child['Size'],
                        'thumbnail': scan.embedded_thumbnail(photo.info.get('exif'))}
    except (ValueError, OSError, SyntaxError, Warning, KeyError, TypeError):
        return None


def reconstruct(fd, total, candidate, photos, cluster, heap, verify):
    """Return exactly one validated join; ambiguity leaves the candidate unresolved."""
    carve = importlib.import_module('carve-photos')
    start, length = candidate['offset'], candidate['bytes']
    thumb = candidate['thumbnail']
    if thumb is None or (start - heap) % cluster or start < heap:
        return None, 'missing_thumbnail_or_unaligned_header'
    auxindex, within = divmod(candidate['preview_logical'], cluster)
    boundaries = min(auxindex + 1, math.ceil(length / cluster))
    if boundaries > MAX_BOUNDARIES:
        return None, 'fragment_search_budget'
    matches, structural = [], []
    for row in photos:
        if row['bytes'] != candidate['preview_bytes'] or (row['offset'] - start) % cluster != within:
            continue
        verify()
        with Image.open(row['output']) as preview:
            if max(preview.size) > 2048 or preview.width * preview.height > 64_000_000:
                continue
            preview.load()
            structural.append(row)
            if scan.thumbnail_difference(preview, thumb) <= 5:
                matches.append(row)
    # A damaged embedded thumbnail can disagree with the camera's own indexed preview.
    if not matches and len(structural) == 1:
        matches = structural
    if len(matches) != 1:
        return None, 'missing_or_ambiguous_preview'
    preview_row = matches[0]
    anchor = preview_row['offset'] - within
    # Read each candidate range once; the boundary search stays in bounded memory.
    tail_base = anchor - (auxindex - 1) * cluster
    tail_end = anchor - auxindex * cluster + length
    if tail_base < heap or tail_end > total or tail_end <= tail_base or start + length > total:
        return None, 'tail_outside_source'
    prefix = os.pread(fd, length, start)
    tail = os.pread(fd, tail_end - tail_base, tail_base)
    if len(prefix) != length or len(tail) != tail_end - tail_base:
        raise OSError('Short fragment source read')
    with Image.open(preview_row['output']) as preview:
        preview.load()
        reference = preview.resize((512, round(512 * candidate['dimensions'][1] / candidate['dimensions'][0])), Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
    accepted = None
    for boundary in range(1, boundaries):
        verify()
        cut = boundary * cluster
        suffix_start = anchor - (auxindex - boundary) * cluster
        if suffix_start == start + cut or (suffix_start < start + cut and suffix_start + length - cut > start):
            continue
        data = prefix[:cut] + tail[(boundary - 1) * cluster:]
        if len(data) != length or data[-2:] != b'\xff\xd9':
            continue
        try:
            n, dimensions = carve.jpeg_extent(None, 0, length, lambda _, count, offset: data[offset:offset + count])
            if n != length or dimensions != candidate['dimensions']:
                continue
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                with Image.open(io.BytesIO(data)) as photo:
                    photo.load()
                    difference = scan.thumbnail_difference(photo, thumb)
                    reduced = photo.resize(reference.size, Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
                    preview_difference = sum(ImageStat.Stat(ImageChops.difference(reduced, reference)).mean) / 3
            if preview_difference > 3:
                continue
        except (ValueError, OSError, SyntaxError, Warning):
            continue
        if accepted is not None:
            return None, 'ambiguous_fragment_joins'
        accepted = {'data': data, 'source_extents': [{'offset': start, 'bytes': cut},
                    {'offset': suffix_start, 'bytes': length - cut}],
                    'thumbnail_difference': difference, 'preview_difference': preview_difference,
                    'paired_preview_offset': preview_row['offset']}
    return accepted, 'reconstructed' if accepted else 'no_valid_two_extent_join'


def recover(fd, total, state, best, verify, checkpoint):
    offsets = state.get('fragment_candidates', [])
    if not offsets:
        return
    geometry_engine = importlib.import_module('fragment-rescue')
    carve = importlib.import_module('carve-photos')
    try:
        geometry = geometry_engine.volume(lambda p, n: os.pread(fd, n, p), total)
    except geometry_engine.Unsupported:
        state['fragment_analysis'] = {'reason': 'unsupported_allocation_geometry'}
        return
    cluster, heap = geometry[3], geometry[4]
    done = state.setdefault('fragment_analysis', {}).setdefault('candidates', {})
    known = {row['offset'] for row in state['photos']}
    sizes = collections.defaultdict(list)
    for row in state['photos']:
        sizes[row['bytes']].append(row)
    print('FRAGMENTS\t' + json.dumps({'done': 0, 'total': len(offsets), 'found': 0}), flush=True)
    for index, start in enumerate(offsets, 1):
        if str(start) in done or start in known:
            continue
        verify()
        candidate = header(fd, start, total)
        if candidate is None:
            done[str(start)] = {'reason': 'unusable_header'}
        else:
            result, reason = reconstruct(fd, total, candidate, sizes[candidate['preview_bytes']], cluster, heap, verify)
            done[str(start)] = {'reason': reason}
            if result is not None:
                verify()
                target = best / f'Photo-{start:012x}.JPG'
                digest = carve.save_exact(target, result.pop('data'))
                row = {'path': target.name, 'output': str(target), 'quality': 'manual_review' if result['thumbnail_difference'] > 5 else 'full_resolution_reconstructed',
                       'offset': start, 'bytes': candidate['bytes'], 'dimensions': candidate['dimensions'],
                       'sha256': digest, 'byte_exact_source_copy': False, 'byte_exact_source_fragments': True,
                       'review_required': True, 'reconstruction': 'mpf_two_extent', **result}
                state['photos'].append(row); known.add(start)
                print('FILE\t' + json.dumps(row), flush=True)
        checkpoint()
        print('FRAGMENTS\t' + json.dumps({'done': index, 'total': len(offsets),
              'found': sum(r.get('reconstruction') == 'mpf_two_extent' for r in state['photos'])}), flush=True)
