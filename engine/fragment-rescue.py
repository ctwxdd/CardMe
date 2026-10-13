"""Bounded exFAT fragment analysis from a read-only byte reader; no private recipes."""
import array
import collections
import itertools
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import warnings
from PIL import Image

scan_engine = importlib.import_module('scan-images')
folder_engine = importlib.import_module('rescue-folder')
MAX_PHOTO = 128 * 1024 * 1024


class Unsupported(ValueError):
    pass


class SourceChanged(ValueError):
    pass


def volume(read, total):
    first = read(0, 512)
    offsets = [0]
    if first[510:512] == b'\x55\xaa':
        for i in range(4):
            start, length = struct.unpack_from('<II', first, 454 + 16 * i)
            if start and length and (start + length) * 512 <= total:
                offsets.append(start * 512)
    # GPT partition starts are metadata, never guessed photo offsets.
    for sector in (512, 4096):
        if total < sector * 2:
            continue
        header = read(sector, 92)
        if header[:8] == b'EFI PART':
            lba, count, size = struct.unpack_from('<QII', header, 72)
            if count > 256 or size < 128 or size > 4096 or lba * sector + count * size > total:
                raise ValueError('Invalid GPT partition table.')
            entries = read(lba * sector, count * size)
            for i in range(count):
                entry = entries[i * size:(i + 1) * size]
                start, end = struct.unpack_from('<QQ', entry, 32)
                if any(entry[:16]) and start <= end and (end + 1) * sector <= total:
                    offsets.append(start * sector)
    for base in dict.fromkeys(offsets):
        if base + 512 > total:
            continue
        boot = read(base, 512)
        if boot[3:11] != b'EXFAT   ':
            continue
        if not 9 <= boot[108] <= 12 or boot[109] > 16 or boot[110] not in (1, 2):
            raise ValueError('Unsupported exFAT geometry.')
        sector = 1 << boot[108]
        cluster = sector << boot[109]
        fat_start, fat_sectors, heap_sectors, count, root = struct.unpack_from('<IIIII', boot, 80)
        active = struct.unpack_from('<H', boot, 106)[0] & 1
        if active >= boot[110] or cluster > 2 * 1024 * 1024 or not 2 <= root < count + 2:
            raise ValueError('Invalid exFAT allocation metadata.')
        fat_offset = base + (fat_start + active * fat_sectors) * sector
        heap = base + heap_sectors * sector
        length = (count + 2) * 4
        if length > 64 * 1024 * 1024 or length > fat_sectors * sector or fat_offset + length > heap or heap + count * cluster > total:
            raise ValueError('exFAT allocation ranges exceed card bounds.')
        return base, boot, sector, cluster, heap, count, root, read(fat_offset, length)
    raise Unsupported('Direct fragment analysis currently supports exFAT cards.')


def recover(read, total, source, scan, output, verify, search_verify=None):
    source = source.resolve()
    output = output.resolve()
    if output.is_relative_to(source):
        raise ValueError('Results must be outside the source card.')
    base, boot, sector, cs, heap, count, root, fat_bytes = volume(read, total)
    fat = list(struct.unpack('<' + str(count + 2) + 'I', fat_bytes))
    fat_offset = base + (struct.unpack_from('<I', boot, 80)[0] + (struct.unpack_from('<H', boot, 106)[0] & 1) * struct.unpack_from('<I', boot, 84)[0]) * sector
    def metadata_unchanged():
        verify()
        current = bytearray(read(base, 512)); expected = bytearray(boot)
        current[106] &= ~2; expected[106] &= ~2
        if current != expected or read(fat_offset, len(fat_bytes)) != fat_bytes:
            raise SourceChanged('Card allocation changed during recovery. Completed copies are preserved; scan again.')
    def valid(c):
        return 2 <= c < count + 2
    def block(c, offset=0, length=None):
        if not valid(c) or offset < 0 or offset >= cs:
            raise ValueError('Cluster outside card allocation.')
        return read(heap + (c - 2) * cs + offset, cs - offset if length is None else length)
    def chain(first, length, contiguous=False, links=None, sequential_break=False):
        links = fat if links is None else links
        needed = (length + cs - 1) // cs
        result, seen, c = [], set(), first
        while valid(c) and c not in seen and len(result) < needed:
            result.append(c); seen.add(c)
            nxt = c + 1 if contiguous else links[c]
            c = c + 1 if sequential_break and not valid(nxt) else nxt
        return result
    # Directory traversal uses the recorded allocation chain, never inferred repairs.
    queue = collections.deque([('', root, None, False)])
    visited, records, directory_bytes = set(), {}, 0
    while queue:
        prefix, first, length, contiguous = queue.popleft()
        if first in visited:
            raise ValueError('Cyclic or aliased exFAT directory.')
        visited.add(first)
        if len(visited) > 4096:
            raise ValueError('Too many directories for bounded analysis.')
        clusters = chain(first, length or 16 * 1024 * 1024, contiguous)
        data = bytearray()
        for c in clusters:
            part = block(c); data.extend(part); directory_bytes += len(part)
            if directory_bytes > 64 * 1024 * 1024:
                raise ValueError('Directory metadata exceeds analysis budget.')
            if any(part[i] == 0 for i in range(0, len(part), 32)):
                break
        i = 0
        while i + 32 <= len(data):
            if data[i] == 0:
                break
            if data[i] != 0x85:
                i += 32; continue
            n = data[i + 1]
            entries = data[i:i + (n + 1) * 32]
            i += (n + 1) * 32
            if n < 2 or n > 18 or len(entries) != (n + 1) * 32 or entries[32] != 0xc0:
                continue
            # Validate the exFAT entry-set checksum before trusting a filename or extent.
            checksum = 0
            for j, value in enumerate(entries):
                if j not in (2, 3):
                    checksum = (((checksum & 1) << 15) + (checksum >> 1) + value) & 65535
            if checksum != struct.unpack_from('<H', entries, 2)[0]:
                continue
            stream = entries[32:64]
            names = b''.join(entries[j + 2:j + 32] for j in range(64, len(entries), 32) if entries[j] == 0xc1)
            name = names[:stream[3] * 2].decode('utf-16-le', errors='strict')
            if not name or name in ('.', '..') or name.startswith('.') or '/' in name or '\\' in name or '\x00' in name:
                continue
            start = struct.unpack_from('<I', stream, 20)[0]
            length = struct.unpack_from('<Q', stream, 24)[0]
            initialized = struct.unpack_from('<Q', stream, 8)[0]
            if not valid(start) or initialized > length or length > count * cs:
                continue
            path = str(Path(prefix) / name)
            contiguous = bool(stream[1] & 2)
            if struct.unpack_from('<H', entries, 4)[0] & 16:
                if length > 16 * 1024 * 1024:
                    raise ValueError('Directory too large for bounded analysis.')
                queue.append((path, start, length, contiguous))
            else:
                records[path.casefold()] = (start, length, contiguous)
    # A displaced FAT sector leaves a run of backwards sequential links. Infer the
    # displacement from this card, and test both allocation hypotheses against pixels.
    repaired = fat.copy()
    shifts = []
    width = sector // 4
    for first in range(width, len(fat) - width, width):
        if sum(count + 2 <= n < 0xfffffff8 for n in fat[first:first + width]) < width // 2:
            continue
        window = range(first + width, min(len(fat), first + width * 32))
        deltas = collections.Counter(c + 1 - fat[c] for c in window if valid(fat[c]) and width <= c + 1 - fat[c] <= width * 4)
        if not deltas:
            continue
        delta, occurrences = deltas.most_common(1)[0]
        if occurrences < 16 or delta % width:
            continue
        last = first
        for start in range(first + width, min(count + 2 - width, first + width * 32), width):
            entries = fat[start:start + width]
            backwards = sum(n == c + 1 - delta for c, n in enumerate(entries, start))
            if backwards:
                last = start + width
            elif last > first and sum(valid(n) for n in entries) > width // 4:
                break
        if last - first <= delta:
            continue
        repaired[first:last - delta] = fat[first + delta:last]
        repaired[last - delta:last] = [0] * delta
        shifts.append({'entries': delta, 'first': first, 'last': last})
    reverse = array.array('I', [0]) * (count + 2)
    terminals = []
    for c, nxt in enumerate(repaired):
        if not valid(c):
            continue
        if valid(nxt):
            reverse[nxt] = c if reverse[nxt] == 0 else 0xffffffff
        elif nxt >= 0xfffffff8:
            terminals.append(c)
    def tails(first, length, entries, mpbase, thumbnail, previews):
        if not entries or mpbase is None or thumbnail is None or len(terminals) > 10000:
            return
        needed = (length + cs - 1) // cs
        for entry in entries[1:]:
            logical = mpbase + entry['DataOffset']
            if not 0 < logical < length or not 0 < entry['Size'] <= MAX_PHOTO:
                continue
            aux_index, within = divmod(logical, cs)
            for terminal in terminals:
                suffix, seen, c = [terminal], {terminal}, terminal
                while valid(reverse[c]) and reverse[c] not in seen and len(suffix) < needed:
                    c = reverse[c]; suffix.append(c); seen.add(c)
                suffix.reverse()
                suffix_index = needed - len(suffix)
                position = aux_index - suffix_index
                if position < 0 or position >= len(suffix):
                    continue
                if block(suffix[position], within, 2) != b'\xff\xd8':
                    continue
                tail = b''.join(block(c) for c in suffix[position:])
                auxiliary = tail[within:within + entry['Size']]
                try:
                    with Image.open(io.BytesIO(auxiliary)) as preview:
                        if preview.width * preview.height > 64_000_000:
                            continue
                        preview.load()
                        if scan_engine.thumbnail_difference(preview, thumbnail) > 5:
                            continue
                except (OSError, ValueError, SyntaxError):
                    continue
                if not previews:
                    previews.append(auxiliary)
                prefix = chain(first, suffix_index * cs, links=repaired, sequential_break=True)
                clusters = prefix + suffix
                if len(prefix) == suffix_index and clusters and clusters[0] == first and len(set(clusters)) == needed:
                    yield clusters
    flagged = [r for r in scan['images'] if not r['status'].startswith('ok_')]
    output.mkdir(parents=True, exist_ok=True)
    best = output / 'best_available'
    if not best.resolve().is_relative_to(output):
        raise ValueError('Result directory redirects outside selected storage.')
    best.mkdir(exist_ok=True)
    results, recipes = [], []
    for index, item in enumerate(flagged, 1):
        path = Path(item['path']).resolve()
        result = {'path': str(path), 'quality': 'manual_review'}
        try:
            if not path.is_relative_to(source) or path.stat().st_size != item['bytes'] or (item.get('mtime_ns') is not None and path.stat().st_mtime_ns != item['mtime_ns']):
                raise ValueError('Photo changed since scanning; scan again.')
            record = records.get(str(path.relative_to(source)).casefold())
            candidate, chosen, previews, orientation = None, None, [], 1
            rebuilt = None
            if record and 0 < record[1] <= MAX_PHOTO:
                first, length, contiguous = record
                header = block(first)
                with Image.open(io.BytesIO(header)) as im:
                    dimensions = im.size
                    orientation = im.getexif().get(274, 1)
                    if dimensions[0] * dimensions[1] > 64_000_000:
                        raise ValueError('Photo exceeds decode budget.')
                    thumbnail = scan_engine.embedded_thumbnail(im.info.get('exif'))
                    try:
                        entries = im.mpinfo[45058]
                    except (AttributeError, KeyError, TypeError):
                        entries = []
                # MPF gives the actual camera stream length when directory lengths were rounded.
                pos, mpbase = 2, None
                while pos + 4 <= len(header) and header[pos:pos + 2] != b'\xff\xda':
                    if header[pos] != 255:
                        break
                    size = struct.unpack_from('>H', header, pos + 2)[0]
                    if size < 2:
                        break
                    if header[pos:pos + 2] == b'\xff\xe2' and header[pos + 4:pos + 8] == b'MPF\0':
                        mpbase = pos + 8
                    pos += 2 + size
                if entries and mpbase is not None:
                    expected = max(e['Size'] + (mpbase + e['DataOffset'] if e['DataOffset'] else 0) for e in entries)
                    if 0 < expected <= MAX_PHOTO:
                        length = expected
                attempts = [chain(first, length, contiguous), chain(first, length, False, repaired),
                            chain(first, length, False, repaired, True), chain(first, length, True)]
                seen = set()
                for clusters in itertools.chain(attempts, tails(first, length, entries, mpbase, thumbnail, previews)):
                    if tuple(clusters) in seen or len(clusters) * cs < length:
                        continue
                    seen.add(tuple(clusters))
                    data = b''.join(block(c) for c in clusters)[:length]
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter('error')
                            with Image.open(io.BytesIO(data)) as im:
                                if im.size != dimensions or thumbnail is None:
                                    continue
                                im.load()
                                if scan_engine.thumbnail_difference(im, thumbnail) > 5:
                                    continue
                                for frame in range(1, min(getattr(im, 'n_frames', 1), 16)):
                                    im.seek(frame); im.load()
                        candidate, chosen = data, clusters
                        break
                    except (OSError, ValueError, SyntaxError, Warning):
                        continue
                if candidate is None:
                    extra = importlib.import_module('normal-jpeg')
                    metadata_unchanged()
                    rebuilt, reason = extra.recover(read, total, heap + (first - 2) * cs, cs, heap,
                                                   terminals, output, search_verify or verify)
                    result['normal_fragment_reason'] = reason
                    if rebuilt:
                        candidate = rebuilt.pop('data')
            if candidate is not None:
                quality = ('manual_review' if rebuilt.get('manual_review') else 'full_resolution_reconstructed') if rebuilt else 'full_resolution'
                suffix, dimensions = '.jpg', list(dimensions)
                if rebuilt:
                    result.update(rebuilt, review_required=True, byte_exact_source_fragments=True)
            else:
                if previews:
                    with Image.open(io.BytesIO(previews[0])) as preview:
                        preview.load()
                        photo = folder_engine.orient(preview.convert('RGB'), orientation)
                    quality = 'camera_preview'
                else:
                    candidate, quality, suffix, dimensions = folder_engine.recover_bytes(path, item)
                if previews:
                    buffer = io.BytesIO(); photo.save(buffer, format='PNG')
                    candidate, suffix, dimensions = buffer.getvalue(), '.rescued.png', list(photo.size)
            metadata_unchanged()
            if path.stat().st_size != item['bytes'] or (item.get('mtime_ns') is not None and path.stat().st_mtime_ns != item['mtime_ns']):
                raise ValueError('Photo changed during recovery.')
            target = best / path.relative_to(source).with_name(path.name if suffix == '.jpg' else path.name + suffix)
            if not target.resolve().is_relative_to(best.resolve()):
                raise ValueError('Output redirects outside result storage.')
            target.parent.mkdir(parents=True, exist_ok=True)
            sha = hashlib.sha256(candidate).hexdigest()
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
                    raise ValueError('Destination differs; refusing to overwrite.')
            else:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                    temp.write(candidate); temp.flush(); os.fsync(temp.fileno()); temporary = Path(temp.name)
                try:
                    verify(); os.link(temporary, target)
                finally:
                    temporary.unlink()
            result.update(quality=quality, output=str(target), dimensions=dimensions, sha256=sha, output_format='JPEG' if suffix == '.jpg' else 'PNG')
            if chosen:
                remaining = len(candidate)
                extents = []
                for c in chosen:
                    length = min(cs, remaining)
                    extents.append({'offset': heap + (c - 2) * cs, 'bytes': length}); remaining -= length
                recipes.append({'path': str(path.relative_to(source)), 'extents': extents, 'sha256': sha, 'dimensions': dimensions})
            elif rebuilt:
                recipes.append({'path': str(path.relative_to(source)), 'extents': rebuilt['source_extents'], 'sha256': sha, 'dimensions': dimensions})
        except (OSError, ValueError, SyntaxError, EOFError, struct.error, Warning) as error:
            if isinstance(error, SourceChanged):
                raise
            result['reason'] = str(error)
        results.append(result)
        print('FILE\t' + json.dumps(result), flush=True)
        print(f'Recovery {index}/{len(flagged)}: {path.name} ({result["quality"]})', flush=True)
    metadata_unchanged()
    report = {'version': 1, 'method': 'direct_exfat_fragment_analysis', 'quality_counts': dict(collections.Counter(r['quality'] for r in results)), 'photos': results,
              'limitations': 'Bounded exFAT allocation hypotheses; no synthesized bytes. Decoding and thumbnail agreement cannot certify every pixel.'}
    for name, data in [('pipeline-report.json', report), ('fragment-map.json', {'version': 1, 'card_bytes': total, 'boot_sha256': hashlib.sha256(boot).hexdigest(), 'fat_sha256': hashlib.sha256(fat_bytes).hexdigest(), 'hypotheses': shifts, 'photos': recipes})]:
        with tempfile.NamedTemporaryFile(mode='w', dir=output, delete=False) as temp:
            json.dump(data, temp, indent=2); temporary = Path(temp.name)
        os.replace(temporary, output / name)
    return 2 if report['quality_counts'].get('manual_review') else 0
