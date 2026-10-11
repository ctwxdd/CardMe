#!/usr/bin/env python3
"""Read-only, filesystem-independent JPEG recovery from a saved card image."""
import argparse, collections, fcntl, hashlib, importlib, io, json, os, signal, sys, tempfile, time, warnings
from pathlib import Path
from PIL import Image
from safety import validate_image_output

scan = importlib.import_module('scan-images')
CHUNK = 8 * 1024 * 1024
MAX_JPEG = 128 * 1024 * 1024
MAX_PIXELS = 64_000_000


class JPEGMarkerError(ValueError):
    """Relative byte offset of a marker-structure failure in a JPEG stream."""
    def __init__(self, message, offset):
        super().__init__(message)
        self.offset = offset


class JPEGMarkerBoundaryError(JPEGMarkerError):
    def __init__(self, offset):
        super().__init__('Invalid JPEG marker boundary', offset)


def jpeg_extent(fd, start, total, pread=None):
    """Walk marker lengths and entropy stuffing; APP thumbnails/FF D9 are not primary endings."""
    pread = pread or os.pread
    cap = min(total, start + MAX_JPEG)
    base, buffer = -1, b''
    def read(pos, count):
        nonlocal base, buffer
        if pos < start or pos + count > cap:
            raise ValueError('Truncated or oversized JPEG')
        if pos < base or pos + count > base + len(buffer):
            base = pos
            buffer = pread(fd, min(256 * 1024, cap - pos), pos)
            if len(buffer) != min(256 * 1024, cap - pos):
                raise OSError('Short source read')
        return buffer[pos-base:pos-base+count]
    def skip_fill(pos):
        while read(pos, 1) == b'\xff':
            part = read(pos, min(4096, cap - pos))
            pos += len(part) - len(part.lstrip(b'\xff'))
        return pos
    if read(start, 2) != b'\xff\xd8':
        raise ValueError('No JPEG start')
    pos, dimensions, scans = start + 2, None, 0
    while pos < cap:
        if read(pos, 1) != b'\xff':
            raise JPEGMarkerBoundaryError(pos - start)
        pos = skip_fill(pos)
        marker = read(pos, 1)[0]; pos += 1
        if marker == 0xD9:
            if not dimensions or not scans:
                raise ValueError('No complete primary JPEG scan')
            return pos - start, dimensions
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7:
            raise JPEGMarkerError('Unexpected JPEG marker', pos - 1 - start)
        if marker == 1:
            continue
        if not (0xC0 <= marker <= 0xFE):
            raise JPEGMarkerError('Invalid JPEG marker', pos - 1 - start)
        size = int.from_bytes(read(pos, 2), 'big')
        if size < 2 or pos + size > cap:
            raise JPEGMarkerError('Invalid JPEG segment length', pos - start)
        if marker in (0xC0, 0xC1, 0xC2):
            body = read(pos + 2, size - 2)
            if len(body) < 6 or body[0] != 8 or size != 8 + 3 * body[5]:
                raise ValueError('Unsupported JPEG frame')
            height, width = int.from_bytes(body[1:3], 'big'), int.from_bytes(body[3:5], 'big')
            if not width or not height or width * height > MAX_PIXELS:
                raise ValueError('JPEG dimensions exceed safety limit')
            dimensions = [width, height]
        pos += size
        if marker != 0xDA:
            continue
        if not dimensions:
            raise ValueError('JPEG scan without frame')
        scans += 1
        while pos < cap:
            read(pos, 1)
            at = buffer.find(b'\xff', pos - base)
            if at == -1:
                pos = base + len(buffer)
                continue
            pos = base + at
            after = pos + 1
            after = skip_fill(after)
            code = read(after, 1)[0]
            if code == 0 or 0xD0 <= code <= 0xD7:
                pos = after + 1
            else:
                break
    raise ValueError('No JPEG end within safety limit')


def photo_quality(photo, difference):
    if difference is not None and difference > 5:
        return 'manual_review'
    if max(photo.size) <= 256:
        return 'thumbnail_only'
    exif = photo.getexif()
    frame = exif.get_ifd(34665) if 34665 in exif else {}
    # Conservatively distinguish camera photos from embedded previews; size alone is insufficient.
    if (max(photo.size) > 2048 and exif.get(271) and exif.get(272)
            and (frame.get(40962), frame.get(40963)) == photo.size):
        return 'full_resolution_copy'
    return 'carved_jpeg'


def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            json.dump(value, out, indent=2)
            out.flush(); os.fsync(out.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_exact(target, data):
    digest = hashlib.sha256(data).hexdigest()
    if target.exists() or target.is_symlink():
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Destination differs; refusing to overwrite: ' + target.name)
        return digest
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(data); out.flush(); os.fsync(out.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    try:
        os.link(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return digest


def recover(image, output):
    image = Path(image).resolve(); output = validate_image_output(image, output)
    stat = image.stat()
    if stat.st_size < 512:
        raise ValueError('The saved card image is too small.')
    identity = {'path': str(image), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'device': stat.st_dev, 'inode': stat.st_ino}
    def verify(fd):
        current = image.stat(); opened = os.fstat(fd)
        expected = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if any((s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) != expected for s in (current, opened)):
            raise ValueError('Source changed. Choose a fresh recovery folder; saved candidates require review.')
    output.mkdir(mode=0o700, exist_ok=True)
    best = output / 'best_available'; report_path = output / 'pipeline-report.json'
    for path in (best, report_path, output / '.pipeline.lock'):
        if path.is_symlink():
            raise ValueError('Refusing redirected recovery output')
    best.mkdir(exist_ok=True)
    with image.open('rb', buffering=0) as disk, (output / '.pipeline.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = disk.fileno()
        if fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_RDONLY:
            raise ValueError('Refusing a writable source descriptor')
        verify(fd)
        try:
            geometry = importlib.import_module('fragment-rescue').volume(lambda p,n: os.pread(fd,n,p), stat.st_size)
        except ValueError:
            geometry = None
        if report_path.exists():
            state = json.loads(report_path.read_text())
            if state.get('identity') != identity or state.get('method') != 'contiguous_jpeg_carving_v1':
                raise ValueError('Source or recovery method changed; choose a fresh output folder.')
        else:
            state = {'version': 1, 'method': 'contiguous_jpeg_carving_v1', 'identity': identity,
                     'next_offset': 0, 'photos': [], 'rejected_candidates': 0, 'fragment_candidates': [], 'fragment_preview_candidates': [], 'jpeg_end_offsets': [], 'complete': False,
                     'limitations': 'JPEG primary streams and bounded MPF-guided two- and three-extent reconstruction plus bounded preview-guided multi-extent candidates for review, including indexed preview recovery. Original filenames and deleted/live status are unknown. Other fragmentation, overwritten and RAW files may remain unresolved. Decoding does not prove every pixel is authentic. No bytes or pixels are synthesized.'}
        offset = state['next_offset']
        if not isinstance(offset, int) or not 0 <= offset <= stat.st_size:
            raise ValueError('Invalid recovery checkpoint')
        known = {row['offset']: row for row in state['photos']}
        # Recheck retained outputs before resuming; never silently reuse a changed photo.
        for row in state['photos']:
            target = best / f"Photo-{row['offset']:012x}.JPG"
            if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('A saved photo changed or is missing; choose a fresh output folder.')
            # Upgrade old completed reports without rescanning the card image or rewriting photos.
            if row['quality'] == 'carved_jpeg':
                with Image.open(target) as photo:
                    row['quality'] = photo_quality(photo, row.get('thumbnail_difference'))
        started = last_update = time.monotonic()
        def checkpoint(complete=False):
            verify(fd)
            state['complete'] = complete
            state['quality_counts'] = dict(collections.Counter(row['quality'] for row in state['photos']))
            state['scanned_bytes'] = state['next_offset']
            atomic_json(report_path, state)
            print('CARVING\t' + json.dumps({'done': state['next_offset'], 'total': stat.st_size, 'found': len(state['photos'])}), flush=True)
        checkpoint()
        try:
            while offset < stat.st_size:
                verify(fd)
                data = os.pread(fd, min(CHUNK, stat.st_size - offset), offset)
                if len(data) != min(CHUNK, stat.st_size - offset):
                    raise OSError('Short source read')
                if geometry is not None:
                    hints = state.setdefault('directory_hints', {})
                    extra_size = min(608, stat.st_size-offset-len(data))
                    extra = os.pread(fd, extra_size, offset+len(data))
                    if len(extra) != extra_size:
                        raise OSError('Short directory hint read')
                    if len(hints) < 100000:
                        for hint in importlib.import_module('orphan-entries').collect(data+extra, offset, geometry[4], geometry[3], geometry[5]):
                            hints[str(hint['directory_entry_offset'])] = hint
                # Retain bounded endpoint hints during the existing scan, avoiding random
                # whole-card endpoint probes when a camera preview is fragmented.
                ends = state.setdefault('jpeg_end_offsets', [])
                end_at = 0
                while len(ends) < 100000:
                    end_at = data.find(b'\xff\xd9', end_at)
                    if end_at < 0:
                        break
                    endpoint = offset + end_at + 2
                    if not ends or endpoint > ends[-1]:
                        ends.append(endpoint)
                    end_at += 2
                cursor = 0
                while True:
                    at = data.find(b'\xff\xd8\xff', cursor)
                    if at < 0:
                        break
                    start = offset + at; cursor = at + 2
                    try:
                        length, dimensions = jpeg_extent(fd, start, stat.st_size)
                        raw = os.pread(fd, length, start)
                        if len(raw) != length:
                            raise OSError('Short JPEG read')
                        try:
                            with warnings.catch_warnings():
                                warnings.simplefilter('error')
                                with Image.open(io.BytesIO(raw)) as photo:
                                    if list(photo.size) != dimensions or photo.format not in ('JPEG', 'MPO'):
                                        raise ValueError('JPEG header differs')
                                    photo.load()
                                    thumb = scan.embedded_thumbnail(photo.info.get('exif'))
                                    difference = scan.thumbnail_difference(photo, thumb) if thumb is not None else None
                                    quality = photo_quality(photo, difference)
                        except OSError as error:
                            raise ValueError('JPEG could not decode') from error
                    except (ValueError, SyntaxError, EOFError, Warning) as error:
                        state['rejected_candidates'] += 1
                        fragments = importlib.import_module('fragment-carve')
                        if fragments.header(fd, start, stat.st_size) is not None:
                            candidates = state.setdefault('fragment_candidates', [])
                            if start not in candidates:
                                candidates.append(start)
                            if isinstance(error, JPEGMarkerError):
                                state.setdefault('fragment_failure_prefixes', {})[str(start)] = {
                                    'offset': error.offset,
                                    'algorithm_version': fragments.ALGORITHM_VERSION}
                        else:
                            preview = importlib.import_module('fragment-preview').describe(fd, start, stat.st_size)
                            if preview is not None:
                                previews = state.setdefault('fragment_preview_candidates', [])
                                if not any(row['offset'] == start for row in previews):
                                    previews.append(preview)
                        continue
                    verify(fd)
                    target = best / f'Photo-{start:012x}.JPG'
                    digest = save_exact(target, raw)
                    row = {'path': target.name, 'output': str(target), 'quality': quality,
                           'offset': start, 'bytes': length, 'dimensions': dimensions, 'sha256': digest,
                           'thumbnail_difference': difference, 'byte_exact_source_copy': True}
                    if start not in known:
                        state['photos'].append(row); known[start] = row
                    print('FILE\t' + json.dumps(row), flush=True)
                    # Skip embedded thumbnails within a successfully decoded primary stream.
                    cursor = at + length
                    if cursor >= len(data):
                        break
                offset = max(offset + max(1, len(data) - 2), offset + cursor)
                offset = min(offset, stat.st_size)
                state['next_offset'] = offset
                if time.monotonic() - last_update >= 1:
                    checkpoint(); last_update = time.monotonic()
            fragments = importlib.import_module('fragment-carve')
            fragments.recover(fd, stat.st_size, state, best, lambda: verify(fd), lambda: checkpoint(False))
            # Orphan entries are naming/length hints, never authority for inferred allocation.
            hints_by_start = collections.defaultdict(list)
            for hint in state.get('directory_hints', {}).values():
                hints_by_start[hint['offset']].append(hint)
            for row in state['photos']:
                hints = hints_by_start[row['offset']]
                names = {h['original_filename_hint'] for h in hints}
                if len(names) == 1:
                    row['original_filename_hint'] = next(iter(names))
                    row['directory_entry_offsets'] = [h['directory_entry_offset'] for h in hints]
            checkpoint(complete=True)
            known = {row['offset']: row for row in state['photos']}
            groups = importlib.import_module('assemble-metadata').assemble(report_path)
            for group in groups:
                row = known[group['preview_offset']]
                row['metadata_output'] = group['metadata_copy']
                row['paired_primary_offset'] = group['primary_offset']
                row['quality'] = 'camera_preview'
            checkpoint(complete=True)
        except KeyboardInterrupt:
            checkpoint()
            raise
        print(f"Finished: {len(state['photos'])} JPEG candidates saved in {time.monotonic()-started:.1f}s. Check the photos before using them.", flush=True)
        return 2 if state['quality_counts'].get('manual_review') else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    return recover(args.image, args.output)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Paused safely. Run again with the same image and output to continue.', flush=True)
        raise SystemExit(130)
    except (OSError, ValueError) as error:
        print('Stopped safely: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
