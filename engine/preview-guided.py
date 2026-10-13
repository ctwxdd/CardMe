"""Bounded baseline JPEG continuation ranking against a surviving camera preview."""
import hashlib
import importlib
import io
import math
import os
import time
import warnings
import subprocess
from PIL import Image, ImageChops, ImageStat

coding = importlib.import_module('jpeg-checkpoint')
native = importlib.import_module('native-ranker')
MAX_SECONDS = 90
MAX_JOINS = 16
LOCAL_CLUSTERS = 256
LOOKAHEAD = 4096
EXPANDED_CLUSTERS = 512


def geometry(raw):
    pos, tables, frame = 2, {}, None
    while pos + 4 <= len(raw):
        if raw[pos] != 255:
            raise coding.Invalid('header marker')
        marker = raw[pos + 1]
        length = int.from_bytes(raw[pos + 2:pos + 4], 'big')
        end = pos + 2 + length
        if length < 2 or end > len(raw):
            raise coding.Invalid('segment bounds')
        data = raw[pos + 4:end]
        pos = end
        if marker == 0xdb:
            index = 0
            while index < len(data):
                key = data[index]; index += 1
                width = 2 if key >> 4 else 1
                if key >> 4 > 1 or index + 64 * width > len(data):
                    raise coding.Invalid('quantization bounds')
                value = int.from_bytes(data[index:index + width], 'big')
                if not value:
                    raise coding.Invalid('zero quantization')
                tables[key & 15] = value
                index += 64 * width
        elif marker == 0xc0:
            if len(data) < 6 or len(data) != 6 + 3 * data[5]:
                raise coding.Invalid('frame bounds')
            frame = (int.from_bytes(data[3:5], 'big'), int.from_bytes(data[1:3], 'big'),
                     [(data[i], data[i + 1] >> 4, data[i + 1] & 15, data[i + 2])
                      for i in range(6, len(data), 3)])
        elif marker == 0xda:
            break
    if not frame or any(q not in tables for _, _, _, q in frame[2]):
        raise coding.Invalid('missing quantization/frame')
    return frame, tables


class PreviewDecoder(coding.Decoder):
    def bit(self, bit):
        before = self.phase
        component = self.blocks[self.block][0]
        block, mcu = self.block, self.mcus
        super().bit(bit)
        if ((before == 'dc_value' and self.phase == 'ac_code')
                or (before == 'dc_code' and self.phase == 'ac_code')):
            value = self.predictors[component]
            if abs(value) > self.limits[component]:
                raise coding.Invalid('DC range')
            if component == self.y_component:
                index = block - self.y_first
                x = (mcu % self.mcu_columns) * self.y_h + index % self.y_h
                y = (mcu // self.mcu_columns) * self.y_v + index // self.y_h
                if x < self.grid.width and y < self.grid.height:
                    self.error_sum += abs(value * self.y_quantization / 8 + 128 - self.grid.getpixel((x, y)))
                    self.error_count += 1

    def clone(self):
        result = super().clone()
        result.error_sum = result.error_count = 0
        return result

    def score(self):
        return self.error_sum / self.error_count if self.error_count else float('inf')


def overlaps(offset, size, extents):
    return any(offset < row['offset'] + row['bytes'] and offset + size > row['offset'] for row in extents)


class SearchBudget(Exception):
    pass


def reconstruct(fd, total, candidate, photos, cluster, heap, verify, pread=None):
    deadline = time.monotonic() + MAX_SECONDS

    def check():
        verify()
        if time.monotonic() >= deadline:
            raise SearchBudget()

    try:
        result, reason = _reconstruct(fd, total, candidate, photos, cluster, heap, check, pread=pread)
        if result is not None or reason not in ('invalid_preview_guided_prefix', 'invalid_prefix_hypothesis'):
            return result, reason
        check()
        result, reason = _reconstruct(fd, total, candidate, photos, cluster, heap, check,
                                      adaptive_prefix=True, pread=pread)
        check()
        return result, reason
    except (SearchBudget, subprocess.TimeoutExpired):
        return None, 'preview_guided_time_budget'


def _reconstruct(fd, total, candidate, photos, cluster, heap, verify, adaptive_prefix=False, pread=None):
    fragments = importlib.import_module('fragment-carve')
    carve = importlib.import_module('carve-photos')
    deadline = time.monotonic() + MAX_SECONDS

    def check():
        verify()  # Source identity and cancellation must propagate to the caller.
        if time.monotonic() >= deadline:
            raise SearchBudget()

    def read(offset, size):
        check()
        raw = (pread or os.pread)(fd, size, offset)
        if len(raw) != size:
            raise OSError('Short preview-guided source read')
        return raw

    def feed(decoder, raw, fd, offset, seconds, verify):
        # Raw cards require aligned reads; use the supplied bytes instead of native rereads.
        if pread is not None:
            return decoder.feed(raw, verify)
        return native.feed(decoder, raw, fd, offset, seconds, verify)

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
    if overlaps(start, cut, owned):
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
        mh, mv = max(c[1] for c in components), max(c[2] for c in components)
        if component != 1 or h != mh or v != mv:
            return None, 'unsupported_preview_sampling'
        with Image.open(preview_row['output']) as preview:
            preview.load()
            decoder.grid = preview.convert('YCbCr').getchannel('Y').resize(
                (math.ceil(width / 8), math.ceil(height / 8)), Image.Resampling.BOX)
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
                    feed(trial, raw[position:end], fd, start+position,
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
                feed(decoder, raw[decoder.header_end:], fd, start+decoder.header_end,
                            max(.1,deadline-time.monotonic()), check)
            except coding.Invalid:
                return None, 'invalid_preview_guided_prefix'
            threshold = max(12, decoder.score() * 6)
        append(start, cut)
        done, physical = cut, start + cut
        while done < length:
            size = min(cluster, length - done)
            trial = decoder.clone()
            valid = not overlaps(physical, size, extents + owned)
            if valid:
                try:
                    feed(trial, read(physical, size), fd, physical,
                                max(.1,deadline-time.monotonic()), check)
                    valid = trial.score() <= threshold
                except coding.Invalid:
                    valid = False
            if not valid:
                if len(joins) >= MAX_JOINS:
                    return None, 'preview_guided_join_budget'
                distances = [0] + [value for n in range(1, LOCAL_CLUSTERS + 1) for value in (n, -n)]
                positions = [physical + n * cluster for n in distances]
                anchor = preview_row['offset'] - within
                auxindex = candidate['preview_logical'] // cluster
                positions.append(anchor - (auxindex - done // cluster) * cluster)
                # Long fragment chains need cheaper ranking probes; full-cluster checks remain mandatory.
                lookahead = 1024 if len(joins) >= 4 else LOOKAHEAD
                def rank_positions(offsets):
                    rows = []
                    eligible = [offset for offset in offsets
                                if offset >= heap and offset + size <= total
                                and not overlaps(offset, size, extents + owned)]
                    if pread is None and native.available(decoder) and eligible:
                        try:
                            eligible = [offset for _,offset in native.screen(decoder, fd,
                                [(0,offset) for offset in eligible], min(512,lookahead,size), total,
                                threshold*2, max(.1,deadline-time.monotonic()), check, allow_empty=True)]
                        except subprocess.TimeoutExpired:
                            raise SearchBudget()
                        if not eligible:
                            return []
                        rows, _ = native.scan(decoder,fd,heap,total,1,min(lookahead,size),
                            len(eligible),max(.1,deadline-time.monotonic()),mode='shortlist',
                            positions=eligible,verify=check)
                        rows.sort()
                        if lookahead < LOOKAHEAD and size > lookahead and rows:
                            rows, _ = native.scan(decoder,fd,heap,total,1,min(LOOKAHEAD,size),
                                min(8,len(rows)),max(.1,deadline-time.monotonic()),mode='shortlist',
                                positions=[offset for _,offset in rows[:8]],verify=check)
                        return sorted(rows)
                    for offset in eligible:
                        probe = decoder.clone()
                        try:
                            raw_probe = read(offset, min(lookahead, size))
                            first = min(512, len(raw_probe))
                            probe.feed(raw_probe[:first], check)
                            if probe.error_count and probe.score() > threshold * 2:
                                continue
                            probe.feed(raw_probe[first:], check)
                        except coding.Invalid:
                            continue
                        if probe.error_count:
                            rows.append((probe.score(), offset))
                    rows.sort()
                    if lookahead < LOOKAHEAD and size > lookahead:
                        refined = []
                        for _, offset in rows[:8]:
                            probe = decoder.clone()
                            try:
                                probe.feed(read(offset, min(LOOKAHEAD, size)), check)
                            except coding.Invalid:
                                continue
                            if probe.error_count:
                                refined.append((probe.score(), offset))
                        rows = sorted(refined)
                    return rows

                ranked = rank_positions(dict.fromkeys(positions))
                # shortcut: greedy full-cluster choice; retain paths only after bounded beam qualification.
                def full_choice(rows):
                    if not rows:
                        return None
                    score, offset = rows[0]
                    trial = decoder.clone()
                    try:
                        feed(trial, read(offset, size), fd, offset,
                                    max(.1,deadline-time.monotonic()), check)
                    except coding.Invalid:
                        return None
                    return (score, offset, trial) if trial.score() <= threshold else None

                accepted = full_choice(ranked)
                if accepted is None:
                    anchor_position = anchor - (auxindex - done // cluster) * cluster
                    expanded_positions = [base + n * cluster for base in (physical, anchor_position)
                                          for n in range(-EXPANDED_CLUSTERS, EXPANDED_CLUSTERS + 1)]
                    previous_positions = set(positions)
                    expanded = rank_positions(offset for offset in dict.fromkeys(expanded_positions)
                                              if offset not in previous_positions)
                    accepted = full_choice(expanded)
                    if accepted is None:
                        return None, 'no_preview_guided_continuation'
                    ranked = expanded
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
