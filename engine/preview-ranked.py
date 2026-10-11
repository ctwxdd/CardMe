"""Bounded baseline JPEG continuation ranking against a surviving camera preview."""
import hashlib
import importlib
import io
import math
import os
import time
import warnings
import importlib.util
from pathlib import Path
import subprocess
_spec = importlib.util.spec_from_file_location("native_probe", Path(__file__).with_name("native-ranker.py"))
native = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(native)
_spec = importlib.util.spec_from_file_location("full_step_cache", Path(__file__).with_name("full-step-cache.py"))
full_cache = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(full_cache)
from PIL import Image, ImageChops, ImageStat

coding = importlib.import_module('jpeg-checkpoint')
MAX_SECONDS = 900
MAX_JOINS = 16


legacy = importlib.import_module('preview-guided')
geometry = legacy.geometry
PreviewDecoder = legacy.PreviewDecoder


def overlaps(offset, size, extents):
    return any(offset < row['offset'] + row['bytes'] and offset + size > row['offset'] for row in extents)


class SearchBudget(Exception):
    pass


def replay_children(path, trace):
    children = []
    for index in range(len(trace) - 1, -1, -1):
        selected = tuple(row['selected'] for row in trace[:index])
        for choice in range(trace[index]['selected'] + 1, trace[index]['options']):
            children.append(selected + (choice,))
    return children


def replay(fd, total, candidate, photos, cluster, heap, verify):
    deadline = time.monotonic() + MAX_SECONDS
    def check():
        verify()
        if time.monotonic() >= deadline:
            raise SearchBudget()
    queue, seen, attempts = [()], set(), []
    while queue and len(attempts) < 32:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        candidate['_replay_path'], candidate['_branch_trace'] = path, []
        try:
            check()
            result, reason = _reconstruct(fd, total, candidate, photos, cluster, heap, check,
                                          adaptive_prefix=True)
            trace = list(candidate['_branch_trace'])
            attempts.append({'path': list(path), 'reason': reason, 'branches': trace})
            candidate['_replay_report'] = attempts
            if result is not None:
                result['replay_attempts'] = len(attempts)
                return result, reason
            if reason == 'preview_guided_time_budget':
                return None, reason
            queue.extend(child for child in replay_children(path, trace) if child not in seen)
        except (SearchBudget, subprocess.TimeoutExpired):
            candidate['_replay_report'] = attempts
            return None, 'preview_guided_time_budget'
    candidate['_replay_report'] = attempts
    return None, 'replay_node_budget' if queue and len(attempts) >= 32 else 'no_valid_replay_path'


def _reconstruct(fd, total, candidate, photos, cluster, heap, verify, adaptive_prefix=False):
    fragments = importlib.import_module('fragment-carve')
    carve = importlib.import_module('carve-photos')
    deadline = time.monotonic() + MAX_SECONDS

    def check():
        verify()  # Source identity and cancellation must propagate to the caller.
        if time.monotonic() >= deadline:
            raise SearchBudget()

    def read(offset, size):
        check()
        raw = os.pread(fd, size, offset)
        if len(raw) != size:
            raise OSError('Short preview-guided source read')
        return raw

    start, length = candidate['offset'], candidate['bytes']
    failure = next((offset for at, offset in candidate.get('_failure_prefixes', []) if at == start), None)
    if failure is None:
        return None, 'missing_prefix_hypothesis'
    original_cut = cut = failure // cluster * cluster
    if adaptive_prefix:
        cut = min(cut, (length - 1) // cluster * cluster)
    if not 0 < cut < length or length > 128 * 1024 * 1024:
        return None, 'invalid_prefix_hypothesis'
    within = candidate['preview_logical'] % cluster
    matches = []
    for row in photos:
        if row['bytes'] != candidate['preview_bytes'] or (row['offset'] - start) % cluster != within:
            continue
        check()
        with Image.open(row['output']) as preview:
            if max(preview.size) > 2048 or preview.width * preview.height > 64_000_000:
                continue
            preview.load()
            if fragments.scan.thumbnail_difference(preview, candidate['thumbnail']) <= 5:
                matches.append(row)
    if len(matches) != 1:
        return None, 'missing_or_ambiguous_preview'
    preview_row = matches[0]
    owned = []
    for row in candidate.get('_known_photos', []):
        if (row.get('offset') == start or row.get('quality') != 'full_resolution_reconstructed'
                or not row.get('source_extents') or not row.get('sha256')):
            continue
        digest = hashlib.sha256()
        for extent in row['source_extents']:
            digest.update(read(extent['offset'], extent['bytes']))
        if digest.hexdigest() != row['sha256']:
            raise ValueError('Changed reconstructed source extents')
        owned.extend(row['source_extents'])
    if not adaptive_prefix and overlaps(start, cut, owned):
        return None, 'occupied_prefix_hypothesis'
    extents, joins = [], []

    def append(offset, size):
        if extents and extents[-1]['offset'] + extents[-1]['bytes'] == offset:
            extents[-1]['bytes'] += size
        else:
            extents.append({'offset': offset, 'bytes': size})

    try:
        raw = read(start, cut)
        decoder = PreviewDecoder(raw)
        (width, height, components), quantization = geometry(raw)
        component, h, v, q = components[0]
        if any(c < 0 or c >= 16 for c, _, _, _ in components):
            return None, 'unsupported_native_components'
        mh, mv = max(c[1] for c in components), max(c[2] for c in components)
        if component != 1 or h != mh or v != mv:
            return None, 'unsupported_preview_sampling'
        with Image.open(preview_row['output']) as preview:
            preview.load()
            decoder.grid = preview.convert('YCbCr').getchannel('Y').resize(
                (math.ceil(width / 8), math.ceil(height / 8)), Image.Resampling.BOX)
            decoder.color_grids = {}
            if candidate.get('_color_ranking'):
                for c, ch, cv, qt in components[1:]:
                    channel = 'Cb' if c == 2 else 'Cr' if c == 3 else None
                    if channel is None:
                        continue
                    grid = preview.convert('YCbCr').getchannel(channel).resize(
                        (math.ceil(width * ch / (8 * mh)), math.ceil(height * cv / (8 * mv))), Image.Resampling.BOX)
                    first = next(i for i, block in enumerate(decoder.blocks) if block[0] == c)
                    decoder.color_grids[c] = (ch, cv, first, quantization[qt], grid)
            reference = preview.resize(fragments.comparison_size(candidate['dimensions']),
                                       Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
        decoder.limits = {c: math.ceil(1024 / quantization[t]) + 1 for c, _, _, t in components}
        decoder.y_component, decoder.y_h, decoder.y_v = component, h, v
        decoder.y_first = next(i for i, b in enumerate(decoder.blocks) if b[0] == component)
        decoder.y_quantization = quantization[q]
        decoder.mcu_columns = math.ceil(width / (mh * 8))
        decoder.error_sum = decoder.error_count = 0
        if adaptive_prefix:
            position = decoder.header_end
            error_sum = error_count = 0
            threshold = 12
            while position < cut:
                end = min(cut, (position // cluster + 1) * cluster)
                trial = decoder.clone()
                try:
                    native.feed(trial, raw[position:end], fd, start+position,
                                max(.1,deadline-time.monotonic()), check)
                    valid = trial.score() <= threshold
                except coding.Invalid:
                    valid = False
                if not valid:
                    cut = position // cluster * cluster
                    if cut <= 0:
                        return None, 'no_valid_initial_cluster'
                    break
                error_sum += trial.error_sum
                error_count += trial.error_count
                decoder, position = trial, end
                threshold = max(12, error_sum / max(1, error_count) * 6)
        else:
            try:
                native.feed(decoder, raw[decoder.header_end:], fd, start+decoder.header_end,
                            max(.1,deadline-time.monotonic()), check)
            except coding.Invalid:
                return None, 'invalid_preview_guided_prefix'
            threshold = max(12, decoder.score() * 6)
        if overlaps(start, cut, owned):
            return None, 'occupied_prefix_hypothesis'
        append(start, cut)
        done, physical = cut, start + cut
        while done < length:
            size = min(cluster, length - done)
            trial = decoder.clone()
            valid = not overlaps(physical, size, extents + owned)
            if valid:
                try:
                    native.feed(trial, read(physical, size), fd, physical,
                                max(.1,deadline-time.monotonic()), check)
                    valid = trial.score() <= threshold
                except coding.Invalid:
                    valid = False
            if not valid:
                if len(joins) >= MAX_JOINS:
                    return None, 'preview_guided_join_budget'
                check()
                seconds = max(.1, deadline - time.monotonic())
                try:
                    ranked, scan_log = native.scan(decoder,
                        fd,
                        heap, min(total,candidate['_active_band_end']), cluster, size if candidate.get('_color_ranking') else min(size, 16384), 512, seconds, excluded=owned+extents, verify=check)
                except subprocess.TimeoutExpired:
                    raise SearchBudget()
                check()
                candidate.setdefault('_native_scans', []).append(scan_log)
                path = candidate.get('_replay_path', ())
                selected = path[len(joins)] if len(joins) < len(path) else 0
                choices = []
                step_cache = {}
                shortlist = ranked[:8] if candidate.get('_color_ranking') else ranked
                if shortlist:
                    shortlist = native.screen(decoder, fd, shortlist, size, total, threshold, max(.1,deadline-time.monotonic()), check)
                for score, offset in shortlist:
                    if offset + size > total or overlaps(offset, size, extents + owned):
                        continue
                    raw_trial = read(offset,size)
                    trial = full_cache.step(decoder, raw_trial, step_cache, check,
                        lambda trial: native.feed(trial,raw_trial,fd,offset,max(.1,deadline-time.monotonic()),check))
                    if trial is None:
                        continue
                    if trial.score() <= threshold:
                        choices.append((score, offset, trial))
                    if len(choices) >= selected + 1:
                        break
                if not choices and candidate['_active_band_end'] < total:
                    check()
                    remaining, scan_log = native.scan(decoder, fd, candidate['_active_band_end'], total, cluster, size if candidate.get('_color_ranking') else min(size,16384), 512, max(.1,deadline-time.monotonic()), excluded=owned+extents, verify=check)
                    shortlist = remaining[:8] if candidate.get('_color_ranking') else remaining
                    if shortlist:
                        shortlist = native.screen(decoder, fd, shortlist, size, total, threshold, max(.1,deadline-time.monotonic()), check)
                    for score,offset in shortlist:
                        if offset+size>total or overlaps(offset,size,owned+extents):continue
                        raw_trial=read(offset,size)
                        trial=full_cache.step(decoder,raw_trial,step_cache,check,
                            lambda trial: native.feed(trial,raw_trial,fd,offset,max(.1,deadline-time.monotonic()),check))
                        if trial is None:continue
                        if trial.score()<=threshold:choices.append((score,offset,trial))
                        if len(choices)>=selected+1:break
                path = candidate.get('_replay_path', ())
                selected = path[len(joins)] if len(joins) < len(path) else 0
                if selected >= len(choices):
                    candidate['_trace'] = {'logical_offset': done, 'cut': cut,
                                           'physical': physical, 'candidates': len(ranked), 'joins': joins}
                    return None, 'no_preview_guided_continuation'
                candidate['_branch_trace'].append({'selected': selected, 'options': 4,
                                                    'logical_offset': done})
                accepted = choices[selected]
                score, physical, trial = accepted
                joins.append({'logical_offset': done, 'source_offset': physical,
                              'preview_luminance_error': score, 'candidates': len(ranked)})
            append(physical, size)
            decoder, done, physical = trial, done + size, physical + size
        if not decoder.eoi or decoder.mcus != decoder.expected:
            return None, 'incomplete_preview_guided_frame'
        data = b''.join(read(row['offset'], row['bytes']) for row in extents)
        # Decode failures reject this hypothesis; source read failures above propagate.
        try:
            encoded, dimensions = carve.jpeg_extent(None, 0, length, lambda _, n, p: data[p:p + n])
            if encoded != length or dimensions != candidate['dimensions']:
                return None, 'invalid_preview_guided_frame'
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                with Image.open(io.BytesIO(data)) as photo:
                    photo.load()
                    difference = fragments.scan.thumbnail_difference(photo, candidate['thumbnail'])
                    reduced = photo.resize(reference.size, Image.Resampling.LANCZOS, reducing_gap=3).convert('RGB')
                    score = sum(ImageStat.Stat(ImageChops.difference(reduced, reference)).mean) / 3
        except (ValueError, OSError, SyntaxError, EOFError, Warning):
            return None, 'invalid_preview_guided_frame'
        if difference > 5 or score > 3:
            return None, 'preview_guided_full_mismatch'
        check()
        return {'data': data, 'source_extents': extents, 'thumbnail_difference': difference,
                'preview_difference': score, 'paired_preview_offset': preview_row['offset'],
                'reconstruction': 'mpf_preview_guided', 'manual_review': True,
                'continuation_decisions': joins, 'prefix_hypothesis_bytes': cut,
                'prefix_rollback_clusters': (original_cut - cut) // cluster}, 'reconstructed_review_candidate'
    except (SearchBudget, subprocess.TimeoutExpired):
        return None, 'preview_guided_time_budget'
    except (coding.Invalid, SyntaxError, EOFError, Warning):
        return None, 'invalid_preview_guided_coding'


def reconstruct(fd, total, candidate, photos, cluster, heap, verify):
    if cluster > 131072 or math.ceil(candidate['dimensions'][0]/8)*math.ceil(candidate['dimensions'][1]/8)>1000000:
        return None, 'unsupported_native_geometry'
    # shortcut: bounded cluster-aligned search; smaller fragments and overwritten data remain unresolved.
    for color in (False, True):
        candidate['_color_ranking'] = color
        result, reason = replay(fd, total, candidate, photos, cluster, heap, verify)
        if result is not None:
            return result, reason
        if reason in ('missing_or_ambiguous_preview', 'missing_prefix_hypothesis', 'occupied_prefix_hypothesis'):
            break
    return None, reason
