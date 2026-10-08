#!/usr/bin/env python3
"""Read-only image scan. Decoding cannot detect every possible pixel corruption."""
import argparse
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import warnings
from PIL import Image, ImageChops, ImageFile, ImageStat
from unittest.mock import patch

ImageFile.LOAD_TRUNCATED_IMAGES = False
SUFFIXES = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.bmp', '.webp', '.avif', '.heic', '.heif', '.ico', '.jp2', '.jxl'}


def embedded_thumbnail(exif):
    """Read the standard EXIF IFD1 JPEG thumbnail, without reading original bytes twice."""
    if not exif or not exif.startswith(b'Exif\0\0'):
        return None
    data = exif[6:]
    order = {b'II': '<', b'MM': '>'}.get(data[:2])
    if order is None:
        raise ValueError('Invalid EXIF byte order')
    def number(code, offset):
        return struct.unpack_from(order + code, data, offset)[0]
    if number('H', 2) != 42:
        raise ValueError('Invalid EXIF TIFF signature')
    first = number('I', 4)
    second = number('I', first + 2 + number('H', first) * 12)
    if not second:
        return None
    tags = {}
    for index in range(number('H', second)):
        entry = second + 2 + index * 12
        tag, kind, count, value = struct.unpack_from(order + 'HHII', data, entry)
        if tag in {513, 514}:
            if kind != 4 or count != 1:
                raise ValueError('Invalid EXIF thumbnail offset/length type')
            tags[tag] = value
    start, length = tags.get(513, 0), tags.get(514, 0)
    if not tags:
        return None
    if not start or not length or start + length > len(data):
        raise ValueError('EXIF thumbnail points outside metadata')
    if length:
        with Image.open(io.BytesIO(data[start:start + length])) as thumb:
            thumb.load()
            return thumb.convert('RGB')
    return None


def thumbnail_difference(image, thumb):
    # Camera thumbnails can letterbox a 3:2 photo inside a 4:3 canvas.
    w, h = thumb.size
    aspect = image.width / image.height
    scores = []
    fitted = (w, max(1, round(w / aspect))) if aspect >= w / h else (max(1, round(h * aspect)), h)
    preview = image.resize(fitted, Image.Resampling.LANCZOS, reducing_gap=3.0).convert('RGB')
    for adjustment in range(-2, 3):
        if aspect >= w / h:
            ch = max(1, min(h, round(w / aspect) + adjustment))
            top = (h - ch) // 2
            crop = thumb.crop((0, top, w, top + ch))
        else:
            cw = max(1, min(w, round(h * aspect) + adjustment))
            left = (w - cw) // 2
            crop = thumb.crop((left, 0, left + cw, h))
        small = preview.resize(crop.size, Image.Resampling.LANCZOS)
        difference = ImageChops.difference(small, crop)
        scores.append(sum(ImageStat.Stat(difference).mean) / 3)
    return min(scores)


def inspect(path, threshold=15, data=None, stop_after='image', opener=None, byte_size=None, quick=False):
    result = {'path': str(path), 'status': 'ok_decoded', 'stages': {}}
    stage = 'read'
    try:
        if byte_size is None and data is None and opener is None:
            result['mtime_ns'] = path.stat().st_mtime_ns
        result['bytes'] = byte_size if byte_size is not None else (len(data) if data is not None else path.stat().st_size)
        open_source = opener or (lambda: io.BytesIO(data) if data is not None else path.open('rb'))
        with open_source() as source, warnings.catch_warnings():
            # A warning at any stage stops the scan instead of continuing to decode.
            warnings.simplefilter('error')
            stage = 'header'
            with Image.open(source) as header:
                result['format'] = header.format
                result['dimensions'] = list(header.size)
                stage = 'thumbnail'
                thumbnail = embedded_thumbnail(header.info.get('exif'))
                result['stages'][stage] = 'passed' if thumbnail is not None else 'absent'
                if stop_after == stage:
                    result['status'] = 'ok_thumbnail'
                    return result
                stage = 'exif'
                exif = header.getexif() if header.format == 'TIFF' else Image.Exif()
                if header.format != 'TIFF' and header.info.get('exif'):
                    exif.load(header.info['exif'])
                for tag in exif:
                    exif[tag]  # Force lazy EXIF values to be parsed.
                    if tag in {34665, 34853}:
                        exif.get_ifd(tag)  # Standard EXIF and GPS subdirectories.
                result['stages'][stage] = 'passed' if exif else 'absent'
                if stop_after == stage:
                    result['status'] = 'ok_exif'
                    return result
                stage = 'image'
                # Canon MPF records the true image sizes: reject impossible lengths
                # before reading image pixels, including truncated but intact EXIF.
                if hasattr(header, 'mpinfo'):
                    entries = header.mpinfo[45058]
                    if sum(entry['Size'] for entry in entries) > result['bytes']:
                        raise ValueError('MPF images exceed file length')
                    for entry in entries:
                        if entry['DataOffset'] + entry['Size'] > result['bytes']:
                            raise ValueError('MPF image points outside file')
                if quick:
                    result['stages'][stage] = 'headers_passed'
                    result['status'] = 'ok_image_header'
                    return result
                header.verify()
            source.seek(0)
            with Image.open(source) as image:
                frames = getattr(image, 'n_frames', 1)
                result['frames'] = frames
                for frame in range(frames):
                    image.seek(frame)
                    image.load()
                    result['decoded_frames'] = frame + 1
                    if frame == 0 and thumbnail is not None:
                        score = thumbnail_difference(image, thumbnail)
                        result['thumbnail_difference'] = round(score, 3)
                        if score > threshold:
                            result.update(status='suspect_thumbnail_mismatch', failed_stage=stage,
                                          reason='Decoded image differs from its embedded thumbnail; inspect visually.')
                            return result
                result['stages'][stage] = 'passed'
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        result.update(status='skipped_size_limit', reason=str(error), failed_stage=stage)
    except Image.UnidentifiedImageError as error:
        status = 'unsupported_or_unrecognized' if path.suffix.lower() in {'.heic', '.heif', '.jxl', '.avif'} else 'decode_error'
        result.update(status=status, reason=str(error), failed_stage=stage)
    except Warning as error:
        result.update(status='suspect_warning', reason=str(error), failed_stage=stage)
    except OSError as error:
        result.update(status='read_error' if error.errno is not None else 'decode_error', reason=str(error), failed_stage=stage)
    except (ValueError, SyntaxError, EOFError, struct.error) as error:
        result.update(status='decode_error', reason=str(error), failed_stage=stage)
    return result


def self_test():
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        valid = folder / 'valid.png'
        Image.new('RGB', (64, 64), 'red').save(valid)
        truncated = folder / 'truncated.png'
        truncated.write_bytes(valid.read_bytes()[:50])
        fake = folder / 'fake.jpg'
        fake.write_bytes(b'not an image')
        assert inspect(valid)['status'] == 'ok_decoded'
        assert inspect(truncated)['status'] == 'decode_error'
        assert inspect(fake)['status'] == 'decode_error'
        assert inspect(folder / 'missing.jpg')['status'] == 'read_error'
        red = Image.new('RGB', (160, 120), 'red')
        assert thumbnail_difference(red, red) == 0
        assert thumbnail_difference(red, Image.new('RGB', red.size, 'blue')) > 100
        jpeg = folder / 'valid.jpg'
        Image.new('RGB', (64, 64), 'red').save(jpeg)
        bad_thumb = folder / 'bad-thumbnail.jpg'
        tiff = b'II' + struct.pack('<HIHIH', 42, 8, 0, 14, 2)
        tiff += struct.pack('<HHIIHHIII', 513, 4, 1, 999999, 514, 4, 1, 10, 0)
        Image.new('RGB', (64, 64), 'red').save(bad_thumb, exif=b'Exif\0\0' + tiff)
        bad_exif = folder / 'bad-exif.jpg'
        tiff = b'II' + struct.pack('<HIH', 42, 8, 1)
        tiff += struct.pack('<HHIII', 34665, 4, 1, 4096, 0)
        Image.new('RGB', (64, 64), 'red').save(bad_exif, exif=b'Exif\0\0' + tiff)
        with patch.object(ImageFile.ImageFile, 'load', side_effect=AssertionError('Full decode reached too early')):
            assert inspect(jpeg, stop_after='thumbnail')['status'] == 'ok_thumbnail'
            assert inspect(jpeg, stop_after='exif')['status'] == 'ok_exif'
            assert inspect(jpeg, quick=True)['status'] == 'ok_image_header'
            assert inspect(bad_thumb)['failed_stage'] == 'thumbnail'
            assert inspect(bad_exif)['failed_stage'] == 'exif'
        assert inspect(jpeg)['status'] == 'ok_decoded'

    print('Self-test passed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', nargs='*', type=Path, help='Image files or folders to scan recursively.')
    parser.add_argument('--report', type=Path, help='New JSON report path, outside the SD card. Existing reports are never overwritten.')
    parser.add_argument('--thumbnail-threshold', type=float, default=15, help='Mismatch threshold, 0–255 (default: 15); mismatches are suspicions, not proof.')
    parser.add_argument('--full', action='store_true', help='Decode all pixels and frames after header checks; default is quick checks only.')
    parser.add_argument('--stop-after', choices=['thumbnail', 'exif', 'image'], default='image', help='Stop after this stage; thumbnail/EXIF passes do not certify image pixels.')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.roots or args.report is None:
        parser.error('Provide at least one image/folder and --report PATH.')
    if not 0 <= args.thumbnail_threshold <= 255:
        parser.error('--thumbnail-threshold must be between 0 and 255.')
    from safety import validate_output
    for root in args.roots:
        validate_output(root, args.report)
        if not root.exists():
            parser.error(f'Input does not exist: {root}')
    # Stream results without retaining decoded images in memory.
    seen = set()
    counts = {}
    unreadable_folders = []
    def files():
        for root in args.roots:
            if root.is_file():
                yield root
            else:
                def walk_error(error):
                    unreadable_folders.append({"path": error.filename, "reason": str(error)})
                for directory, directories, names in os.walk(root, onerror=walk_error, followlinks=False):
                    directories[:] = sorted(name for name in directories if not name.startswith(".") and not (Path(directory) / name).is_symlink())
                    for name in sorted(names):
                        path = Path(directory) / name
                        if not name.startswith('._') and path.suffix.lower() in SUFFIXES and not path.is_symlink():
                            yield path
    with args.report.open('x', encoding='utf-8') as report:
        report.write('{"limitations":"Quick checks do not validate image pixels; use --full for pixel decoding. Successful decoding does not prove every pixel is intact. RAW files are not checked. Unsupported formats and thumbnail mismatches need review.","images":[\n')
        first = True
        for path in files():
            path = path.resolve()
            if path in seen:
                continue
            seen.add(path)
            result = inspect(path, args.thumbnail_threshold, stop_after=args.stop_after, quick=not args.full)
            counts[result['status']] = counts.get(result['status'], 0) + 1
            print('SCANNING\t' + json.dumps({'checked': len(seen)}), flush=True)
            if not first:
                report.write(',\n')
            report.write(json.dumps(result, ensure_ascii=False))
            report.flush()
            first = False
            if not result['status'].startswith('ok_'):
                print('FILE\t' + json.dumps(result, ensure_ascii=False), flush=True)
                print(result['status'], path, result.get('reason', ''), flush=True)
            if len(seen) % 100 == 0:
                print(f'Scanned {len(seen)} images...', file=sys.stderr, flush=True)
        report.write('\n],"counts":' + json.dumps(counts) + ',"unreadable_folders":' + json.dumps(unreadable_folders) + '}\n')
    print(json.dumps(counts, indent=2))
    print('Report:', args.report)


if __name__ == '__main__':
    main()
