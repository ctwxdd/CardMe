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
MAX_GAPS = 4096
MAX_THREE_JOIN_ATTEMPTS = 8192


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
    if accepted:
        return accepted, 'reconstructed'
    three = reconstruct_three(fd, total, candidate, photos, cluster, heap, verify)
    if three is not None:
        return three, 'reconstructed'
    return None, 'no_valid_two_extent_join'


def reconstruct_three(fd, total, candidate, photos, cluster, heap, verify):
    """Try unique prefix/gap/tail joins; marker failure and free space are hypotheses."""
    carve = importlib.import_module('carve-photos')
    start, length = candidate['offset'], candidate['bytes']
    # Only a failed marker boundary supplies a prefix hypothesis. Re-read it on resume,
    # since older reports did not retain this diagnostic.
    try:
        carve.jpeg_extent(fd, start, total)
    except carve.JPEGMarkerBoundaryError as error:
        failure = error.offset
    except (ValueError, SyntaxError, EOFError, Warning):
        return None
    else:
        return None
    prefix_clusters = failure // cluster
    if prefix_clusters <= 0 or prefix_clusters * cluster >= length:
        return None
    prefix_bytes = prefix_clusters * cluster
    auxindex, within = divmod(candidate['preview_logical'], cluster)
    if auxindex <= prefix_clusters or math.ceil(length / cluster) > MAX_BOUNDARIES:
        return None

    # Mark only source extents already reported as recovered and the candidate's
    # observed prefix. The first marker failure never proves the exact fragment cut.
    count = math.ceil((total - heap) / cluster)
    if count <= 0 or count > 16_000_000:
        return None
    used = bytearray(count)
    def mark(offset, size):
        first = max(0, (offset - heap) // cluster)
        last = min(count, math.ceil((offset + size - heap) / cluster))
        if last > first:
            used[first:last] = b'\1' * (last - first)
    def mark_row(row):
        extents = row.get('source_extents')
        if extents:
            for extent in extents:
                mark(extent['offset'], extent['bytes'])
        else:
            mark(row['offset'], row['bytes'])
    for row in candidate.get('_known_photos', ()):
        mark_row(row)
    for row in photos:
        mark_row(row)
    mark(start, prefix_bytes)
    gaps = []
    i = 0
    while i < count:
        if used[i]:
            i += 1; continue
        first = i
        while i < count and not used[i]:
            i += 1
        gaps.append((heap + first * cluster, (i - first) * cluster))
        if len(gaps) > MAX_GAPS:
            return None

    matches = []
    for row in photos:
        if row['bytes'] != candidate['preview_bytes'] or (row['offset'] - start) % cluster != within:
            continue
        verify()
        with Image.open(row['output']) as preview:
            if max(preview.size) <= 2048 and preview.width * preview.height <= 64_000_000:
                preview.load()
                if scan.thumbnail_difference(preview, candidate['thumbnail']) <= 5:
                    matches.append(row)
    if len(matches) != 1:
        return None
    preview_row = matches[0]
    anchor = preview_row['offset'] - within
    anchor_cluster = (anchor - heap) // cluster
    # Locate the unowned run immediately before the tail anchor; nearby logical
    # boundaries account for allocation rounding without trusting the marker offset.
    tail_cluster = anchor_cluster
    while tail_cluster > 0 and tail_cluster - 1 < count and not used[tail_cluster - 1]:
        tail_cluster -= 1
    if tail_cluster == anchor_cluster:
        return None
    first_tail = auxindex - (anchor_cluster - tail_cluster)
    if first_tail <= prefix_clusters:
        return None

    prefix = os.pread(fd, prefix_bytes, start)
    if len(prefix) != prefix_bytes:
        raise OSError('Short fragment prefix read')
    with Image.open(preview_row['output']) as preview:
        preview.load()
        reference = preview.resize((512, round(512 * candidate['dimensions'][1] / candidate['dimensions'][0])), Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
    accepted = []
    attempts = 0
    for boundary in range(first_tail, min(first_tail + 4, math.ceil(length / cluster))):
        if boundary <= prefix_clusters:
            continue
        middle_bytes = (boundary - prefix_clusters) * cluster
        suffix_start = anchor - (auxindex - boundary) * cluster
        tail_bytes = length - boundary * cluster
        if tail_bytes <= 0 or suffix_start < heap or suffix_start + tail_bytes > total:
            continue
        tail = os.pread(fd, tail_bytes, suffix_start)
        if len(tail) != tail_bytes or tail[-2:] != b'\xff\xd9':
            continue
        for gap_start, gap_bytes in gaps:
            if gap_bytes < middle_bytes:
                continue
            for middle_start in {gap_start, gap_start + gap_bytes - middle_bytes}:
                if attempts >= MAX_THREE_JOIN_ATTEMPTS:
                    return None
                if middle_start < heap or middle_start + middle_bytes > total:
                    continue
                if not (middle_start + middle_bytes <= start or middle_start >= start + prefix_bytes):
                    continue
                if not (middle_start + middle_bytes <= suffix_start or middle_start >= suffix_start + tail_bytes):
                    continue
                verify(); attempts += 1
                middle = os.pread(fd, middle_bytes, middle_start)
                if len(middle) != middle_bytes:
                    raise OSError('Short fragment middle read')
                data = prefix + middle + tail
                try:
                    n, dimensions = carve.jpeg_extent(None, 0, length, lambda _, size, offset: data[offset:offset + size])
                    if n != length or dimensions != candidate['dimensions']:
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter('error')
                        with Image.open(io.BytesIO(data)) as photo:
                            photo.load()
                            difference = scan.thumbnail_difference(photo, candidate['thumbnail'])
                            reduced = photo.resize(reference.size, Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
                            score = sum(ImageStat.Stat(ImageChops.difference(reduced, reference)).mean) / 3
                    if difference > 5 or score > 3:
                        continue
                except (ValueError, OSError, SyntaxError, EOFError, Warning):
                    continue
                accepted.append({'data': data, 'source_extents': [
                    {'offset': start, 'bytes': prefix_bytes},
                    {'offset': middle_start, 'bytes': middle_bytes},
                    {'offset': suffix_start, 'bytes': tail_bytes}],
                    'thumbnail_difference': difference, 'preview_difference': score,
                    'paired_preview_offset': preview_row['offset']})
                if len(accepted) > 1:
                    return None
    return accepted[0] if len(accepted) == 1 else None


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
        if (str(start) in done and done[str(start)].get('reason') != 'no_valid_two_extent_join') or start in known:
            continue
        verify()
        candidate = header(fd, start, total)
        if candidate is None:
            done[str(start)] = {'reason': 'unusable_header'}
        else:
            candidate['_known_photos'] = state['photos']
            result, reason = reconstruct(fd, total, candidate, sizes[candidate['preview_bytes']], cluster, heap, verify)
            done[str(start)] = {'reason': reason}
            if result is not None:
                verify()
                target = best / f'Photo-{start:012x}.JPG'
                digest = carve.save_exact(target, result.pop('data'))
                row = {'path': target.name, 'output': str(target), 'quality': 'manual_review' if result['thumbnail_difference'] > 5 else 'full_resolution_reconstructed',
                       'offset': start, 'bytes': candidate['bytes'], 'dimensions': candidate['dimensions'],
                       'sha256': digest, 'byte_exact_source_copy': False, 'byte_exact_source_fragments': True,
                       'review_required': True, 'reconstruction': 'mpf_three_extent' if len(result['source_extents']) == 3 else 'mpf_two_extent', **result}
                state['photos'].append(row); known.add(start)
                print('FILE\t' + json.dumps(row), flush=True)
        checkpoint()
        print('FRAGMENTS\t' + json.dumps({'done': index, 'total': len(offsets),
              'found': sum(str(r.get('reconstruction', '')).startswith('mpf_') for r in state['photos'])}), flush=True)
