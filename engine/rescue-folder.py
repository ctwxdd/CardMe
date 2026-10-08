#!/usr/bin/env python3
"""Rescue readable primary images/previews/thumbnails from flagged files, read-only."""
import argparse, collections, fcntl, hashlib, importlib, io, json, os, signal, struct, tempfile, warnings
from pathlib import Path
from PIL import Image, ImageOps
from safety import validate_output
scan = importlib.import_module('scan-images')


def recover(path, flagged):
    """Decode the primary image; require thumbnail agreement when one is available."""
    thumbnail, orientation = None, 1
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        with Image.open(path) as image:
            thumbnail = scan.embedded_thumbnail(image.info.get('exif'))
            try:
                orientation = image.getexif().get(274, 1)
            except (OSError, ValueError, SyntaxError, Warning):
                pass
            # ponytail: embedded data only; missing filesystem fragments need a disk image.
            try:
                frames = min(getattr(image, 'n_frames', 1), 16)
            except (OSError, ValueError, SyntaxError, struct.error):
                frames = 1
            for frame in range(frames):
                try:
                    image.seek(frame)
                    image.load()
                    if thumbnail is not None and scan.thumbnail_difference(image, thumbnail) > 5:
                        continue
                    candidate = image.convert('RGB')
                    quality = 'full_resolution_copy' if frame == 0 else 'camera_preview'
                    return orient(candidate, orientation), quality
                except (OSError, ValueError, SyntaxError, EOFError, struct.error, Warning):
                    continue
    if thumbnail is not None:
        return orient(thumbnail, orientation), 'thumbnail_only'
    raise ValueError('No intact embedded photo or thumbnail was available.')


def orient(image, orientation):
    exif = Image.Exif()
    exif[274] = orientation if orientation in range(1, 9) else 1
    image.info['exif'] = exif.tobytes()
    return ImageOps.exif_transpose(image)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--scan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    source = args.source.resolve()
    if not source.is_dir():
        raise ValueError('Select the same photo folder used for scanning.')
    output = validate_output(source, args.output)
    report = json.loads(args.scan.read_text())
    flagged = [r for r in report['images'] if not r['status'].startswith('ok_')]
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / '.pipeline.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    best = output / 'best_available'
    if not best.resolve().is_relative_to(output):
        raise ValueError('Output folder redirects outside private storage.')
    best.mkdir(exist_ok=True)
    results = []
    for index, item in enumerate(flagged, 1):
        path = Path(item['path']).resolve()
        result = {'path': str(path), 'quality': 'manual_review'}
        try:
            if not path.is_relative_to(source) or path.is_symlink():
                raise ValueError('Scan entry is outside the selected source.')
            before = path.stat()
            if before.st_size != item['bytes'] or (item.get('mtime_ns') is not None and before.st_mtime_ns != item['mtime_ns']):
                raise ValueError('Source changed since scanning; scan again.')
            photo, quality = recover(path, item)
            data = io.BytesIO()
            photo.save(data, format='PNG')
            pixels = data.getvalue()
            with Image.open(io.BytesIO(pixels)) as check:
                check.load()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Source changed during recovery.')
            target = best / path.relative_to(source).with_name(path.name + '.rescued.png')
            target = target.resolve()
            if not target.is_relative_to(best.resolve()) or target.is_relative_to(source):
                raise ValueError('Destination redirects outside private result storage.')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != pixels:
                    raise ValueError('Destination differs; refusing to overwrite.')
            else:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                    temporary = Path(temp.name)
                    temp.write(pixels)
                    temp.flush()
                    os.fsync(temp.fileno())
                try:
                    os.link(temporary, target)
                finally:
                    temporary.unlink()
            result.update(quality=quality, output=str(target), dimensions=list(photo.size), sha256=hashlib.sha256(pixels).hexdigest())
        except (OSError, ValueError, SyntaxError, EOFError, struct.error, Image.DecompressionBombError, Warning) as error:
            result['reason'] = str(error)
        results.append(result)
        print('FILE\t' + json.dumps(result), flush=True)
        print(f"Recovery {index}/{len(flagged)}: {path.name} ({result['quality']})", flush=True)
    summary = {'version': 1, 'quality_counts': dict(collections.Counter(r['quality'] for r in results)), 'photos': results,
               'limitations': 'Embedded-data rescue only. Full-resolution copies are re-encoded, not byte-identical originals. Decoding and thumbnail agreement do not certify every pixel. Missing fragments require deeper recovery.'}
    with tempfile.NamedTemporaryFile(mode='w', dir=output, delete=False) as temp:
        json.dump(summary, temp, indent=2)
        temporary = Path(temp.name)
    os.replace(temporary, output / 'pipeline-report.json')
    print('Finished:', summary['quality_counts'], flush=True)
    return 2 if summary['quality_counts'].get('manual_review') else 0


if __name__ == '__main__':
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('Interrupted. Completed rescued files were preserved.', flush=True)
        raise SystemExit(130)
    except (OSError, ValueError, KeyError) as error:
        print('Stopped safely:', error, flush=True)
        raise SystemExit(1)
