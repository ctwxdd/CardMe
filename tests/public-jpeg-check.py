#!/usr/bin/env python3
"""Offline public-content regression; reference bytes are never search input."""
import hashlib, importlib, io, json, os, struct, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'engine'))
folder = root / 'tests/fixtures/public-jpeg'
manifest = json.loads((folder / 'manifest.json').read_text())
for row in manifest['files']:
    raw = (folder / row['file']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], row['file']
allocation = importlib.import_module('fragment-rescue')
normal = importlib.import_module('normal-jpeg')
imaging = importlib.import_module('image-card')
metadata = importlib.import_module('assemble-metadata')
rescue = importlib.import_module('rescue-folder')
carve = importlib.import_module('carve-photos')

def jpeg(image, **kwargs):
    stream = io.BytesIO(); image.save(stream, format='JPEG', quality=95, **kwargs)
    return stream.getvalue()


def fixture(name, cut_clusters, orientation):
    # These public pixels are resized/re-encoded to create a camera-like MPF fixture.
    # Synthetic EXIF/MPF must not be mistaken for metadata present in the public source.
    with Image.open(folder / name) as original:
        photo = original.convert('RGB').resize((2400, 1600), Image.Resampling.LANCZOS)
    preview = jpeg(photo.resize((1620, 1080), Image.Resampling.LANCZOS))
    exif = Image.Exif(); exif[271] = 'CardMe public regression'; exif[272] = 'Synthetic MPF'; exif[274] = orientation
    with Image.open(io.BytesIO(jpeg(photo, exif=exif))) as donor:
        tags = metadata.preview_exif(donor, photo.size, photo.resize((160, 107)))
    plain = metadata.replace_exif(jpeg(photo), tags)
    length, logical = len(plain) + 90, len(plain) + 90 + 128
    mpf = b'II*\0' + struct.pack('<IH', 8, 3)
    mpf += struct.pack('<HHI', 0xB000, 7, 4) + b'0100'
    mpf += struct.pack('<HHII', 0xB001, 4, 1, 2) + struct.pack('<HHII', 0xB002, 7, 32, 50) + bytes(4)
    mpf += struct.pack('<IIIHH', 0x80030000, length, 0, 2, 0)
    mpf += struct.pack('<IIIHH', 0x40010002, len(preview), logical - 10, 0, 0)
    primary = plain[:2] + b'\xff\xe2' + struct.pack('>H', len(mpf) + 6) + b'MPF\0' + mpf + plain[2:]
    cluster, heap = 32768, 32768
    start, cut, suffix = heap + cluster * 4, cluster * cut_clusters, heap + cluster * 1024
    assert cut < len(primary)
    child = suffix + logical - cut
    payload = bytearray(child + len(preview) + cluster)
    payload[start:start+cut] = primary[:cut]
    payload[start+cut:start+cut+16] = b'\xff\xd8' + bytes(14)
    payload[suffix:suffix+length-cut] = primary[cut:]
    payload[child:child+len(preview)] = preview
    payload.extend(bytes((-len(payload) + heap) % cluster))
    count = (len(payload)-heap)//cluster
    # Use real exFAT geometry and directory parsing; only the damaged allocation chain is incomplete.
    payload[3:11] = b'EXFAT   '; payload[108:111] = bytes([9, 6, 1]); payload[510:512] = b'\x55\xaa'
    struct.pack_into('<IIIII', payload, 80, 1, 63, 64, count, 2)
    fat = [0]*(count+2); fat[2] = 0xffffffff
    first = 2+(start-heap)//cluster
    for c in range(first, first+cut//cluster-1): fat[c] = c+1
    terminal = 2+(child+len(preview)-1-heap)//cluster; fat[terminal] = 0xffffffff
    struct.pack_into('<' + str(len(fat)) + 'I', payload, 512, *fat)
    filename = 'IMG_1234.JPG'; expected = primary + bytes(128) + preview
    entry = bytearray(96); entry[0] = 0x85; entry[1] = 2; entry[4] = 32
    entry[32] = 0xc0; entry[33] = 1; entry[35] = len(filename)
    struct.pack_into('<Q', entry, 40, len(expected)); struct.pack_into('<I', entry, 52, first); struct.pack_into('<Q', entry, 56, len(expected))
    entry[64] = 0xc1; entry[66:66+len(filename)*2] = filename.encode('utf-16-le')
    checksum = 0
    for i, value in enumerate(entry):
        if i not in (2, 3): checksum = (((checksum&1)<<15)+(checksum>>1)+value)&65535
    struct.pack_into('<H', entry, 2, checksum); payload[heap:heap+96] = entry
    return payload, expected, primary[:cut], (start, cluster, heap, terminal), filename

started = time.monotonic(); results = []
# Preserve upstream baseline JPEGs; document the arithmetic-marker parser limit.
for name in ['testorig.jpg', 'testimgint.jpg', 'testimgari.jpg']:
    source = folder / name; original = source.read_bytes()
    data, quality, suffix, dimensions = rescue.recover_bytes(source, {})
    if name == 'testimgari.jpg':
        assert quality == 'full_resolution_copy' and suffix == '.rescued.png' and data.startswith(b'\x89PNG')
        with Image.open(source) as a, Image.open(io.BytesIO(data)) as b:
            assert a.convert('RGB').tobytes() == b.convert('RGB').tobytes()
        kind = 'arithmetic_jpeg_png_fallback'
    else:
        assert data == original and quality == 'full_resolution' and suffix == '.jpg', name
        carve.jpeg_extent(None, 0, len(data), lambda _, n, p: data[p:p+n])
        kind = 'unchanged_public_jpeg'
    assert source.read_bytes() == original
    results.append({'case': name, 'kind': kind, 'sha256': hashlib.sha256(data).hexdigest(), 'dimensions': dimensions})

# Upstream testimgint is sequential, not progressive; create a labelled derived case.
with tempfile.TemporaryDirectory(prefix='CardMe-public-progressive-') as temporary:
    source = Path(temporary)/'derived-progressive.jpg'
    with Image.open(folder/'testorig.jpg') as image:
        image.save(source, format='JPEG', quality=95, progressive=True)
    original = source.read_bytes()
    data, quality, suffix, dimensions = rescue.recover_bytes(source, {})
    assert data == original and quality == 'full_resolution' and suffix == '.jpg'
    with Image.open(source) as check: assert check.info.get('progressive') or check.info.get('progression')
    results.append({'case': 'derived-progressive.jpg', 'kind': 'public_content_progressive', 'sha256': hashlib.sha256(data).hexdigest(), 'dimensions': dimensions})

for name, cut, orientation in [('shira_bird8.bmp', 2, 8), ('shira_bird8.bmp', 4, 6), ('vgl_5674_0098.png', 4, 6)]:
    payload, expected, prefix, geometry, filename = fixture(name, cut, orientation)
    with tempfile.TemporaryDirectory(prefix='CardMe-public-regression-') as temporary:
        base = Path(temporary); source = base/'card'; source.mkdir(); photo = source/filename; photo.write_bytes(prefix)
        image = base/'simulated-card.img'; image.write_bytes(payload); image.chmod(0o444)
        output = base/'rescued'; before = hashlib.sha256(payload).hexdigest()
        scan = {'images': [{'path': str(photo), 'status': 'decode_error', 'bytes': len(prefix), 'mtime_ns': photo.stat().st_mtime_ns}]}
        fd = os.open(image, os.O_RDONLY); actual_pread = os.pread
        def aligned(fd, size, offset):
            assert size%512 == offset%512 == 0, (size, offset)
            return actual_pread(fd, size, offset)
        def read(offset, size): return imaging.read_card_range(fd, offset, size, len(payload), 512)
        try:
            with patch.object(os, 'pread', side_effect=aligned):
                assert allocation.recover(read, len(payload), source, scan, output, lambda: None) == 0
            row = json.loads((output/'pipeline-report.json').read_text())['photos'][0]
            saved = Path(row['output']); data = saved.read_bytes()
            # Ground truth is consulted only after the public recovery entrypoint returns.
            if name == 'vgl_5674_0098.png':
                # Complete source bytes do not override a failed thumbnail/preview agreement check.
                assert row['quality'] == 'thumbnail_only' and row['normal_fragment_reason'] == 'matching_preview_not_found_in_normal_search', row
                assert data.startswith(b'\x89PNG') and data != expected
                kind = 'high_detail_preview_agreement_refusal'
            else:
                assert data == expected and row['quality'] == 'full_resolution_reconstructed', row
                assert b''.join(payload[e['offset']:e['offset']+e['bytes']] for e in row['source_extents']) == data
                with Image.open(saved) as decoded:
                    assert decoded.getexif()[274] == orientation; decoded.load(); assert decoded.size == (2400,1600)
                    decoded.seek(1); decoded.load(); assert decoded.size == (1620,1080)
                kind = 'two_part_synthetic_mpf'
            assert hashlib.sha256(image.read_bytes()).hexdigest() == before and photo.read_bytes() == prefix
            assert not list(output.glob('.normal-jpeg-*')) and not list(output.rglob('*.img'))
            results.append({'case': name, 'kind': kind, 'cut_clusters': cut, 'orientation': orientation, 'sha256': hashlib.sha256(data).hexdigest(), 'search_bytes': row.get('normal_search_bytes')})
        finally: os.close(fd)

assert len(results) == 7
report = {'dataset_commit': manifest['commit'], 'case_count': len(results), 'reconstruction_successes': sum(r['kind'] == 'two_part_synthetic_mpf' for r in results), 'known_limitations': sum(r['kind'] in ('arithmetic_jpeg_png_fallback', 'high_detail_preview_agreement_refusal') for r in results), 'cases': results, 'seconds': round(time.monotonic()-started, 3), 'source_unchanged': True}
(root/'work').mkdir(exist_ok=True)
(root/'work/public-jpeg-regression.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
