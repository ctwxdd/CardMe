#!/usr/bin/env python3
"""Read-only card recovery, with optional verified recipes and JPEG carving."""
import argparse, collections, fcntl, hashlib, importlib, io, json, os, signal, stat as statlib, subprocess, sys, tempfile, time
from safety import validate_output
decisions = importlib.import_module("decision-model")
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent

def digest(data):
    return hashlib.sha256(data).hexdigest()

def boot_matches(data, expected):
    # exFAT's volume-dirty bit changes on mount; it does not change photo allocation.
    if digest(data) == expected:
        return True
    return len(data) == 512 and data[3:11] == b'EXFAT   ' and digest(data[:106] + bytes([data[106] & ~2]) + data[107:]) == expected

def atomic_json(path, value):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        temp = Path(out.name)
        json.dump(value, out, indent=2)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, path)

def analyze_card(args, image, output):
    imaging = importlib.import_module('image-card')
    analysis = importlib.import_module('fragment-rescue')
    expected = (args.registry_id, args.bytes)
    card = imaging.device_identity(args.device)
    before = image.stat()
    if card[:2] != expected or not statlib.S_ISCHR(before.st_mode):
        raise ValueError('The selected card changed. Select it again.')
    print('Analyzing photo allocation directly from your card, read only…', flush=True)
    fd = imaging.authorized_read(str(image))
    try:
        if os.fstat(fd).st_rdev != before.st_rdev:
            raise ValueError('The selected card changed during authorization.')
        checked_at = 0.0
        read_bytes = 0
        def verify(force=True):
            nonlocal checked_at
            now = time.monotonic()
            if force or now - checked_at >= 0.25:
                if imaging.device_identity(args.device)[:2] != expected:
                    raise ValueError('The card was disconnected or changed. Completed copies are preserved.')
                checked_at = now
        def read(offset, length):
            nonlocal read_bytes
            verify(False)
            data = imaging.read_card_range(fd, offset, length, args.bytes, card[2])
            read_bytes += ((offset + length + card[2] - 1) // card[2] - offset // card[2]) * card[2]
            return data
        output.mkdir(parents=True, exist_ok=True)
        with (output / '.pipeline.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                result = analysis.recover(read, args.bytes, args.source.resolve(), json.loads(args.scan.read_text()), output, verify)
                report = json.loads((output / 'pipeline-report.json').read_text())
                report['source_bytes_read_this_run'] = read_bytes
                report['identity'] = {'device': args.device, 'registry_id': args.registry_id, 'bytes': args.bytes}
                atomic_json(output / 'pipeline-report.json', report)
                return result
            except analysis.Unsupported as error:
                print(str(error) + ' Trying readable photos instead.', flush=True)
    finally:
        os.close(fd)
    return importlib.import_module('rescue-folder').main(['--source', str(args.source), '--scan', str(args.scan), '--output', str(output)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--image', type=Path)
    inputs.add_argument('--device')
    parser.add_argument('--registry-id', type=int)
    parser.add_argument('--bytes', type=int)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--scan', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    image = Path('/dev/r' + args.device) if args.device else args.image.resolve()
    output = args.output.resolve()
    if not args.device and not image.is_file():
        raise ValueError('A saved regular-file card image is required.')
    if args.device and (args.registry_id is None or args.bytes is None or args.source is None or args.scan is None):
        raise ValueError('Card identity, photo folder and scan report are required.')
    if bool(args.source) != bool(args.scan):
        raise ValueError('A photo folder and its scan report must be provided together.')
    output = validate_output(image, output)
    def folder_fallback():
        print('No matching fragment map. Trying the readable photo files…', flush=True)
        return importlib.import_module('rescue-folder').main(['--source', str(args.source),
                                                            '--scan', str(args.scan), '--output', str(output)])
    profile_path = ROOT / 'verified-rescue-profile.json'
    directory = ROOT / 'card_directory.json'
    if not profile_path.is_file() or not directory.is_file():
        if args.device:
            return analyze_card(args, image, output)
        return importlib.import_module('carve-photos').recover(image, output)
    profile_bytes = profile_path.read_bytes()
    profile = json.loads(profile_bytes)
    if digest(directory.read_bytes()) != profile['directory_sha256']:
        raise ValueError('Directory snapshot differs from the verified profile.')
    # The public engine has no snapshot scanner; saved images use general JPEG carving.
    if not args.device and not args.scan:
        return importlib.import_module('carve-photos').recover(image, output)
    if args.device and args.bytes != profile['image_bytes']:
        return folder_fallback()
    stat = image.stat()
    total = args.bytes if args.device else stat.st_size
    identity = {'path': str(image), 'size': total, 'mtime_ns': None if args.device else stat.st_mtime_ns,
                'profile_sha256': digest(profile_bytes)}
    if args.device:
        imaging = importlib.import_module('image-card')
        expected = (args.registry_id, args.bytes)
        card = imaging.device_identity(args.device)
        if card[:2] != expected or not statlib.S_ISCHR(stat.st_mode):
            raise ValueError('The selected card changed. Select it again.')
        print('Reading only the required photo regions. macOS may ask for read-only card access…', flush=True)
        fd = imaging.authorized_read(str(image))
        if os.fstat(fd).st_rdev != stat.st_rdev:
            os.close(fd)
            raise ValueError('The selected card changed during authorization.')
        identity['registry_id'] = args.registry_id
    def verify():
        if args.device and imaging.device_identity(args.device)[:2] != expected:
            raise ValueError('The card was disconnected or changed. Completed copies are preserved.')
    source_bytes = 0
    with os.fdopen(fd, 'rb', buffering=0) if args.device else image.open('rb') as disk:
        verify()
        def read(offset, length):
            nonlocal source_bytes
            verify()
            if offset < 0 or length < 0 or offset + length > total:
                raise ValueError('Recovery extent outside image.')
            if args.device:
                data = imaging.read_card_range(disk.fileno(), offset, length, total, card[2])
                source_bytes += ((offset + length + card[2] - 1) // card[2] - offset // card[2]) * card[2]
                return data
            disk.seek(offset)
            data = disk.read(length)
            source_bytes += len(data)
            if len(data) != length:
                raise ValueError('Short source read.')
            return data
        if total != profile['image_bytes'] or not boot_matches(read(profile['partition_offset'], 512), profile['boot_sha256']) or digest(read(profile['fat_offset'], profile['fat_bytes'])) != profile['fat_sha256']:
            if args.device:
                return folder_fallback()
            print('Searching this safety copy for photos beyond the file list…', flush=True)
            return importlib.import_module('carve-photos').recover(image, output)
        output.mkdir(parents=True, exist_ok=True)
        with (output / '.pipeline.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state_path = output / 'pipeline-state.json'
            state = json.loads(state_path.read_text()) if state_path.exists() else {'identity': identity, 'completed': {}}
            if state['identity'] != identity:
                raise ValueError('Source changed; choose a fresh output folder.')
            # ponytail: verified fragment recipes remain snapshot-specific; other saved images use contiguous JPEG carving.
            scan_path = output / 'pipeline-scan.json'
            scan_start = time.monotonic()
            scan_reused = bool(state.get('scan_sha256') and scan_path.exists() and digest(scan_path.read_bytes()) == state['scan_sha256'])
            if args.scan:
                scan = json.loads(args.scan.read_text())
                source = args.source.resolve()
                for item in scan['images']:
                    path = Path(item['path']).resolve()
                    if not path.is_relative_to(source):
                        raise ValueError('Scan entry is outside the selected source.')
                    item['original_path'] = item['path']
                    item['path'] = str(Path('DCIM') / path.parent.name / path.name)
                atomic_json(scan_path, scan)
                scan_reused = True  # already scanned through the normal folder path
            elif scan_reused:
                print('Scan: reused unchanged checkpoint.', flush=True)
            else:
                raise ValueError('A scan report is required for verified fragment recovery.')
            scan_seconds = time.monotonic() - scan_start
            scan = json.loads(scan_path.read_text())
            flagged = [r for r in scan['images'] if not r['status'].startswith('ok_')]
            recipes = {r['logical_path']: r for r in profile['photos']}
            ranking = decisions.rank([{'id': r['path'], 'quality': recipes.get(r['path'], {}).get('quality'),
                                       'verified_recipe': r['path'] in recipes,
                                       'bytes': sum(e['bytes'] for e in recipes.get(r['path'], {}).get('extents', [])),
                                       'extents': len(recipes.get(r['path'], {}).get('extents', []))} for r in flagged])
            by_path = {r['path']: r for r in flagged}
            flagged = [by_path[r['id']] for r in ranking]
            best = output / 'best_available'
            best.mkdir(exist_ok=True)
            results, reused = [], 0
            for index, item in enumerate(flagged, 1):
                recipe = recipes.get(item['path'])
                if recipe is None:
                    result = {'path': item.get('original_path', item['path']), 'quality': 'manual_review', 'reason': 'No verified recovery recipe.'}
                    results.append(result)
                    print('FILE\t' + json.dumps(result), flush=True)
                    continue
                target = best / recipe['output_name']
                try:
                    if target.exists():
                        if digest(target.read_bytes()) != recipe['output_sha256']:
                            raise ValueError('Destination differs; refusing to overwrite.')
                        reused += 1
                        action = 'reused'
                    else:
                        data = b''.join(read(e['offset'], e['bytes']) for e in recipe['extents'])
                        if digest(data) != recipe['source_sha256']:
                            raise ValueError('Recovered source bytes differ from verified repair.')
                        with Image.open(io.BytesIO(data)) as photo:
                            dimensions = list(photo.size)
                            for frame in range(getattr(photo, 'n_frames', 1)):
                                photo.seek(frame)
                                photo.load()
                            photo.seek(0)
                            if recipe['quality'] != 'full_resolution':
                                with Image.open(io.BytesIO(read(recipe['header_offset'], 131072))) as header:
                                    orientation = header.getexif().get(274, 1)
                                exif = Image.Exif()
                                exif[274] = orientation
                                photo.info['exif'] = exif.tobytes()
                                converted = ImageOps.exif_transpose(photo)
                                dimensions = list(converted.size)
                                buffer = io.BytesIO()
                                converted.save(buffer, format='PNG')
                                data = buffer.getvalue()
                        if dimensions != recipe['expected_dimensions'] or digest(data) != recipe['output_sha256']:
                            raise ValueError('Output failed verified dimensions/hash checks.')
                        with tempfile.NamedTemporaryFile(dir=best, delete=False) as temp:
                            temp_path = Path(temp.name)
                            temp.write(data)
                            temp.flush()
                            os.fsync(temp.fileno())
                        try:
                            verify()
                            os.link(temp_path, target)  # Atomic publication without replacing any file.
                        finally:
                            temp_path.unlink()
                        action = 'restored'
                    verify()
                    result = {'path': item.get('original_path', item['path']), 'quality': recipe['quality'], 'output': str(target), 'sha256': recipe['output_sha256'], 'dimensions': recipe['expected_dimensions']}
                    state['completed'][item['path']] = result
                    atomic_json(state_path, state)
                    results.append(result)
                    print('FILE\t' + json.dumps(result), flush=True)
                    print(f"Recovery {index}/{len(flagged)}: {recipe['name']} {action} ({recipe['quality']})", flush=True)
                except (OSError, ValueError, SyntaxError) as exc:
                    result = {'path': item.get('original_path', item['path']), 'quality': 'manual_review', 'reason': str(exc)}
                    results.append(result)
                    print('FILE\t' + json.dumps(result), flush=True)
                    print(f"Recovery {index}/{len(flagged)}: needs review: {exc}", flush=True)
            verify()
            current = image.stat()
            if not args.device and (current.st_size, current.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                raise ValueError('Source changed during the run; outputs require review.')
            report = {'version': 1, 'identity': identity, 'quality_counts': dict(collections.Counter(r['quality'] for r in results)),
                      'decision_ranking': ranking, 'scanned_images': len(scan['images']), 'flagged_images': len(flagged), 'reused_outputs': reused,
                      'scan_seconds': scan_seconds, 'elapsed_seconds': time.monotonic() - start,
                      'source_bytes_read_this_run': source_bytes + (sum(r['bytes_read'] for r in scan['images']) + profile['fat_bytes'] + 512 if not scan_reused else 0),
                      'scan_requested_photo_bytes': sum(r.get('bytes_read', 0) for r in scan['images']),
                      'limitations': 'Quick scan does not certify pixel integrity. Verified recipes apply only to this supplied profile. Preview and thumbnail results are lower resolution.', 'photos': results}
            atomic_json(output / 'pipeline-report.json', report)
            print(f"Finished in {report['elapsed_seconds']:.2f}s: {report['quality_counts']}; reused {reused}.", flush=True)
            return 2 if report['quality_counts'].get('manual_review') else 0

if __name__ == '__main__':
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nInterrupted. Run the same command to resume.', file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Stopped safely: {exc}', file=sys.stderr)
        raise SystemExit(1)
