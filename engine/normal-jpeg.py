"""Selected-photo reconstruction through the existing aligned, read-only card reader."""
import heapq, importlib, io, math, tempfile, time, warnings
from pathlib import Path
from PIL import Image

fragments = importlib.import_module('fragment-carve')
carve = importlib.import_module('carve-photos')
guided = importlib.import_module('preview-guided')
MAX_SECONDS = 90
MAX_BYTES = 256 * 1024 * 1024
MAX_PREVIEW_PROBES = 4096


class SearchLimit(Exception):
    pass


def recover(read, total, start, cluster, heap, terminals, output, verify, known=()):
    deadline = time.monotonic() + MAX_SECONDS
    used = 0
    def check():
        verify()
        if time.monotonic() >= deadline:
            raise SearchLimit()
    def pread(_, size, offset):
        nonlocal used
        check()
        if offset < 0 or size < 0 or offset + size > total:
            raise ValueError('Normal reconstruction read outside card.')
        if used + size > MAX_BYTES:
            raise SearchLimit()
        used += size
        data = read(offset, size)
        if len(data) != size:
            raise OSError('Short normal reconstruction read.')
        return data
    try:
        candidate = fragments.header(None, start, total, pread=pread)
        if candidate is None or candidate['thumbnail'] is None:
            return None, 'missing_camera_index_or_thumbnail'
        candidate['_known_photos'] = list(known)
        try:
            carve.jpeg_extent(None, start, total, pread)
        except carve.JPEGMarkerError as error:
            candidate['_failure_prefixes'] = [(start, error.offset)]
        except (ValueError, SyntaxError, EOFError, Warning):
            pass
        within = candidate['preview_logical'] % cluster
        expected = start + candidate['preview_logical']
        positions = {expected + distance * cluster for distance in range(-512, 513)}
        # Allocation endpoints and nearby cluster positions are clues, never old-card recipes.
        nearby_terminals = heapq.nsmallest(MAX_PREVIEW_PROBES, terminals,
            key=lambda c: abs(heap + (c - 2) * cluster - expected))
        for terminal in nearby_terminals:
            check()
            for back in range(min(64, math.ceil(candidate['preview_bytes'] / cluster) + 1)):
                positions.add(heap + (terminal - 2 - back) * cluster + within)
        positions = sorted((p for p in positions if heap <= p and p + candidate['preview_bytes'] <= total),
                           key=lambda p: (abs(p - expected), p))[:MAX_PREVIEW_PROBES]
        with tempfile.TemporaryDirectory(prefix='.normal-jpeg-', dir=output) as temporary:
            previews = []
            for position in positions:
                if pread(None, 2, position) != b'\xff\xd8':
                    continue
                raw = pread(None, candidate['preview_bytes'], position)
                try:
                    length, dimensions = carve.jpeg_extent(None, 0, len(raw), lambda _, n, p: raw[p:p+n])
                    if length != len(raw) or max(dimensions) > 2048:
                        continue
                    with warnings.catch_warnings():
                        warnings.simplefilter('error')
                        with Image.open(io.BytesIO(raw)) as preview:
                            preview.load()
                            if fragments.scan.thumbnail_difference(preview, candidate['thumbnail']) > 5:
                                continue
                except (ValueError, OSError, SyntaxError, Warning):
                    continue
                path = Path(temporary) / f'{position}.jpg'
                path.write_bytes(raw)
                previews.append({'offset': position, 'bytes': len(raw), 'output': str(path)})
                if len(previews) > 1:
                    return None, 'missing_or_ambiguous_preview'
            if not previews:
                return None, 'matching_preview_not_found_in_normal_search'
            rebuilt, reason = fragments.reconstruct(None, total, candidate, previews, cluster, heap, check, pread=pread)
            if rebuilt is None and reason in ('no_valid_two_extent_join', 'missing_prefix_hypothesis'):
                rebuilt, reason = guided.reconstruct(None, total, candidate, previews, cluster, heap, check, pread=pread)
            if rebuilt is None:
                return None, reason
            # Retain the indexed preview and intervening source bytes when the physical tail agrees.
            last = rebuilt['source_extents'][-1]
            tail_end = last['offset'] + last['bytes']
            gap = candidate['preview_logical'] - len(rebuilt['data'])
            preview = previews[0]
            if gap >= 0 and tail_end + gap == preview['offset']:
                extra = pread(None, gap + preview['bytes'], tail_end)
                rebuilt['data'] += extra
                rebuilt['source_extents'].append({'offset': tail_end, 'bytes': len(extra)})
                with warnings.catch_warnings():
                    warnings.simplefilter('error')
                    with Image.open(io.BytesIO(rebuilt['data'])) as check_image:
                        for frame in range(min(getattr(check_image, 'n_frames', 1), 16)):
                            check_image.seek(frame); check_image.load()
            else:
                rebuilt['manual_review'] = True
            rebuilt['reconstruction'] = rebuilt.get('reconstruction', 'normal_mpf_fragment_join')
            rebuilt['normal_search_bytes'] = used
            return rebuilt, reason
    except SearchLimit:
        return None, 'normal_fragment_search_budget'
