#!/usr/bin/env python3
"""Pair saved previews with camera EXIF; never change source JPEGs or invent photo pixels."""
import argparse, functools, hashlib, importlib, io, json, struct, warnings
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

scan = importlib.import_module('scan-images')
carve = importlib.import_module('carve-photos')


def replace_exif(raw, metadata=b''):
    if raw[:2] != b'\xff\xd8':
        raise ValueError('Not a JPEG')
    output = bytearray(raw[:2])
    if metadata:
        if len(metadata) > 65533:
            raise ValueError('EXIF exceeds JPEG segment limit')
        output += b'\xff\xe1' + struct.pack('>H', len(metadata) + 2) + metadata
    pos = 2
    while pos < len(raw):
        start = pos
        if raw[pos] != 255:
            raise ValueError('Invalid JPEG marker')
        while pos < len(raw) and raw[pos] == 255:
            pos += 1
        marker = raw[pos]; pos += 1
        if marker in (0xDA, 0xD9):
            output += raw[start:]
            return bytes(output)
        if marker == 1:
            output += raw[start:pos]
            continue
        length = int.from_bytes(raw[pos:pos+2], 'big')
        end = pos + length
        if length < 2 or end > len(raw):
            raise ValueError('Truncated JPEG')
        if not (marker == 0xE1 and raw[pos+2:pos+8] == b'Exif\0\0'):
            output += raw[start:end]
        pos = end
    raise ValueError('Incomplete JPEG')


def preview_exif(donor, size, thumb):
    source = donor.getexif(); result = Image.Exif()
    # Only descriptive tags: never transplant GPS, serials, MakerNote or offset-bearing data.
    for tag in (271, 272, 274, 306):
        if tag in source:
            result[tag] = source[tag]
    original = source.get_ifd(34665) if 34665 in source else {}
    frame = {tag: original[tag] for tag in (36867, 36868, 36880, 36881, 36882, 37520, 37521, 37522) if tag in original}
    frame.update({40962: size[0], 40963: size[1]}); result[34665] = frame
    metadata = bytearray(result.tobytes())
    # Append a standard IFD1 thumbnail while leaving all IFD0/subdirectory offsets intact.
    endian = '<' if metadata[6:8] == b'II' else '>'
    root = struct.unpack_from(endian+'I', metadata, 10)[0] + 6
    count = struct.unpack_from(endian+'H', metadata, root)[0]
    next_ifd = root + 2 + count * 12
    thumbnail = io.BytesIO(); thumb.save(thumbnail, format='JPEG', quality=90)
    payload = thumbnail.getvalue(); ifd = len(metadata)-6
    struct.pack_into(endian+'I', metadata, next_ifd, ifd)
    start = ifd + 2 + 4*12 + 4
    metadata += struct.pack(endian+'H', 4)
    for tag, kind, value in ((259, 3, 6), (274, 3, result.get(274, 1)), (513, 4, start), (514, 4, len(payload))):
        metadata += struct.pack(endian+'HHI', tag, kind, 1)
        metadata += struct.pack(endian+'H', value)+b'\0\0' if kind == 3 else struct.pack(endian+'I', value)
    metadata += bytes(4) + payload
    return bytes(metadata)


def assemble(report_path):
    report_path = Path(report_path).resolve()
    state = json.loads(report_path.read_text())
    if not state.get('complete') or state.get('method') != 'contiguous_jpeg_carving_v1':
        raise ValueError('A completed JPEG recovery report is required')
    output = report_path.parent / 'best_available' / 'Metadata Copies'
    if output.is_symlink():
        raise ValueError('Refusing redirected metadata output')
    rows = sorted(state['photos'], key=lambda r: r['offset'])
    @functools.lru_cache(maxsize=64)
    def thumbnail(path):
        with Image.open(path) as photo:
            return scan.embedded_thumbnail(photo.info.get('exif'))
    @functools.lru_cache(maxsize=32)
    def visual(path):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(path) as photo:
                photo.draft('RGB', (512, 512)); photo.load()
                return photo.resize((256, 171), Image.Resampling.LANCZOS).convert('RGB')
    donors = []
    for row in rows:
        path = Path(row['output'])
        if path.is_symlink() or path.parent.resolve() != report_path.parent / 'best_available':
            raise ValueError('Unexpected saved-photo path')
        with Image.open(path) as photo:
            exif = photo.getexif()
            if max(photo.size) <= 2048 or not exif.get(271) or not exif.get(272):
                continue
            if photo.info.get('exif'):
                frame = exif.get_ifd(34665) if 34665 in exif else {}
                donors.append((row, photo.size, (exif.get(271), exif.get(272), frame.get(36867))))
    groups = []; matched = 0
    for row in rows:
        if row['quality'] not in ('carved_jpeg', 'camera_preview') or not 256 < max(row['dimensions']) <= 2048:
            continue
        with Image.open(row['output']) as preview:
            tags = preview.getexif()
            if tags.get(274):
                continue
            frame = tags.get_ifd(34665) if 34665 in tags else {}
            identity = (tags.get(271), tags.get(272), frame.get(36867))
            preview.draft('RGB', (256, 256)); preview.load()
            candidates = []; eligible = []
            for donor, size, donor_identity in donors:
                if any(left and right and left != right for left, right in zip(identity, donor_identity)):
                    continue
                if abs(donor['offset']-row['offset']) > 32*1024*1024:
                    continue
                if abs(size[0]/size[1] - row['dimensions'][0]/row['dimensions'][1]) > .02:
                    continue
                eligible.append(donor)
                thumb = thumbnail(donor['output'])
                if thumb is None:
                    continue
                difference = scan.thumbnail_difference(preview, thumb)
                candidates.append((difference, donor, thumb))
        candidates.sort(key=lambda c: c[0])
        comparison = 'embedded_thumbnail'
        if not candidates or candidates[0][0] > 5 or (len(candidates)>1 and candidates[1][0]-candidates[0][0] < 2):
            # A camera thumbnail may differ in crop/color; compare the primary image before giving up.
            scores = []
            reference = visual(row['output'])
            for donor in eligible:
                try:
                    difference = sum(ImageStat.Stat(ImageChops.difference(reference, visual(donor['output']))).mean) / 3
                except (OSError, ValueError, Warning):
                    continue
                scores.append((difference, donor))
            scores.sort(key=lambda value: value[0])
            if not scores or scores[0][0] > 3 or (len(scores)>1 and scores[1][0]-scores[0][0] < 1.5):
                continue
            difference, donor = scores[0]
            comparison = 'primary_pixels'
            # Build this copy's thumbnail from its own image, rather than copying a suspect thumbnail.
            with Image.open(row['output']) as photo:
                photo.draft('RGB', (256, 256)); photo.load()
                thumb = photo.convert('RGB'); thumb.thumbnail((160, 120), Image.Resampling.LANCZOS)
        else:
            difference, donor, thumb = candidates[0]
        original = Path(row['output']).read_bytes(); primary = Path(donor['output']).read_bytes()
        if hashlib.sha256(original).hexdigest() != row['sha256'] or hashlib.sha256(primary).hexdigest() != donor['sha256']:
            raise ValueError('Saved photo changed; metadata pairing stopped')
        with Image.open(io.BytesIO(primary)) as photo:
            metadata = preview_exif(photo, row['dimensions'], thumb)
        repaired = replace_exif(original, metadata)
        if replace_exif(repaired) != replace_exif(original):
            raise ValueError('JPEG image stream changed')
        with Image.open(io.BytesIO(repaired)) as check:
            check.load()
            if list(check.size) != row['dimensions']:
                raise ValueError('Metadata copy dimensions changed')
        output.mkdir(mode=0o700, exist_ok=True)
        target = output / Path(row['output']).name
        digest = carve.save_exact(target, repaired)
        groups.append({'primary': donor['output'], 'preview': row['output'], 'metadata_copy': str(target),
                       'primary_offset': donor['offset'], 'preview_offset': row['offset'], 'difference': difference, 'comparison': comparison,
                       'sha256': digest, 'metadata_inferred': True, 'image_stream_unchanged': True})
        matched += 1
        if matched % 100 == 0:
            print(f'Metadata: {matched} previews paired', flush=True)
    manifest = report_path.parent / 'metadata-assembly.json'
    if manifest.is_symlink():
        raise ValueError('Refusing redirected manifest')
    carve.atomic_json(manifest, {'version': 1, 'groups': groups, 'matched_previews': matched,
                                'note': 'Original JPEGs retain their original EXIF and thumbnails. Metadata copies infer selected tags from an unambiguous nearby visual match; original filenames and missing image pixels are not restored.'})
    print(f'Metadata: {matched} previews paired; source photos unchanged.', flush=True)
    return groups


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('report', type=Path)
    assemble(parser.parse_args().report)
