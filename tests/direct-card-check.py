#!/usr/bin/env python3
"""Read-only card recovery with synthetic profile and public fallbacks."""
import hashlib, importlib, io, json, os, stat, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'engine'))
rescue = importlib.import_module('sd-rescue')
imaging = importlib.import_module('image-card')
sha = lambda data: hashlib.sha256(data).hexdigest()
with tempfile.TemporaryDirectory(prefix='cardrescue-direct-check-') as temp:
    base = Path(temp)
    engine = base / 'engine'
    engine.mkdir()
    source = base / 'source'
    photos = source / 'DCIM/101CANON'
    photos.mkdir(parents=True)
    photo = photos / 'test.jpg'
    buffer = io.BytesIO()
    Image.new('RGB', (32, 24), 'red').save(buffer, format='JPEG')
    jpeg = buffer.getvalue()
    photo.write_bytes(jpeg)
    unknown = photos / 'unknown.jpg'
    unknown.write_bytes(b'not a jpeg')
    scan = base / 'scan.json'
    rows = [{'path': str(p), 'status': 'decode_error', 'failed_stage': 'image', 'bytes': p.stat().st_size,
             'mtime_ns': p.stat().st_mtime_ns} for p in [photo, unknown]]
    scan.write_text(json.dumps({'images': rows}))
    card = base / 'fixture.img'
    data = bytearray(4 * 1024 * 1024)
    boot = bytearray(b'B' * 512)
    boot[3:11] = b'EXFAT   '
    boot[106:108] = b'\x00\x00'
    boot, fat = bytes(boot), b'F' * 512
    dirty = boot[:106] + b'\x02' + boot[107:]
    assert rescue.boot_matches(dirty, sha(boot))
    assert not rescue.boot_matches(boot[:106] + b'\x01' + boot[107:], sha(boot))  # active FAT cannot change
    data[:512], data[4096:4608] = boot, fat
    data[12001:12201] = jpeg[:200]
    data[17003:17003 + len(jpeg) - 200] = jpeg[200:]
    card.write_bytes(data)
    (engine / 'card_directory.json').write_text('[]')
    profile = {'image_bytes': len(data), 'partition_offset': 0, 'boot_sha256': sha(boot),
               'fat_offset': 4096, 'fat_bytes': 512, 'fat_sha256': sha(fat),
               'directory_sha256': sha(b'[]'), 'photos': [
        {'name': 'test.jpg', 'logical_path': 'DCIM/101CANON/test.jpg', 'quality': 'full_resolution',
         'output_name': 'test.jpg', 'expected_dimensions': [32, 24],
         'extents': [{'offset': 12001, 'bytes': 200}, {'offset': 17003, 'bytes': len(jpeg) - 200}],
         'source_sha256': sha(jpeg), 'output_sha256': sha(jpeg)}]}
    (engine / 'verified-rescue-profile.json').write_text(json.dumps(profile))
    raw = Path('/dev/rdisk999999')
    real_stat = Path.stat
    def source_stat(path, *args, **kwargs):
        if path == raw:
            return SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=0)
        return real_stat(path, *args, **kwargs)
    descriptors = []
    def authorize(path):
        assert path == str(raw)
        fd = os.open(card, os.O_RDONLY)
        descriptors.append(fd)
        return fd
    def run(output, size=len(data), identity=None):
        argv = ['sd-rescue.py', '--device', 'disk999999', '--registry-id', '44', '--bytes', str(size),
                '--source', str(source), '--scan', str(scan), '--output', str(output)]
        with patch.object(rescue, 'ROOT', engine), patch.object(sys, 'argv', argv), \
             patch.object(Path, 'stat', source_stat), patch.object(imaging, 'authorized_read', side_effect=authorize), \
             patch.object(imaging, 'device_identity', side_effect=identity or (lambda _: (44, len(data), 512))):
            return rescue.main()
    profile_path = engine / 'verified-rescue-profile.json'
    directory_path = engine / 'card_directory.json'
    profile_bytes, directory_bytes = profile_path.read_bytes(), directory_path.read_bytes()
    profile_path.unlink()
    directory_path.unlink()
    descriptor_count = len(descriptors)
    no_profile = base / 'no-profile'
    card.write_bytes(bytes(data[:3]) + b'NOTFAT  ' + bytes(data[11:]))
    assert run(no_profile) == 2
    assert len(descriptors) == descriptor_count + 1  # public analysis requests a read-only descriptor
    card.write_bytes(data)
    assert json.loads((no_profile / 'pipeline-report.json').read_text())['quality_counts'] == {
        'full_resolution_copy': 1, 'manual_review': 1}
    saved_image = base / 'saved.img'
    saved_image.write_bytes(jpeg)
    saved_output = base / 'saved-image-results'
    with patch.object(rescue, 'ROOT', engine), patch.object(sys, 'argv', [
        'sd-rescue.py', '--image', str(saved_image), '--output', str(saved_output)
    ]):
        assert rescue.main() == 0
    carved = next((saved_output / 'best_available').iterdir())
    assert carved.read_bytes() == jpeg
    assert saved_image.read_bytes() == jpeg
    profile_path.write_bytes(profile_bytes)
    directory_path.write_bytes(directory_bytes)
    output = base / 'results'
    assert run(output) == 2
    report = json.loads((output / 'pipeline-report.json').read_text())
    assert report['quality_counts'] == {'full_resolution': 1, 'manual_review': 1}
    assert report['photos'][0]['path'] == str(photo)
    assert (output / 'best_available/test.jpg').read_bytes() == jpeg
    assert report['source_bytes_read_this_run'] < 4096  # metadata plus two selected, aligned fragments
    assert not list(output.rglob('*.img'))
    data[106] = 2  # mounted/unclean state changes must not reject the same verified fragments
    card.write_bytes(data)
    assert run(output) == 2
    assert json.loads((output / 'pipeline-report.json').read_text())['reused_outputs'] == 1
    (output / 'best_available/test.jpg').write_bytes(b'conflict')
    assert run(output) == 2
    assert (output / 'best_available/test.jpg').read_bytes() == b'conflict'
    cancelled = base / 'cancelled'
    with patch.object(imaging, 'read_card_range', side_effect=KeyboardInterrupt):
        try:
            run(cancelled)
            raise AssertionError('Cancellation ignored')
        except KeyboardInterrupt:
            assert not cancelled.exists()
    calls = 0
    def changed(_):
        global calls
        calls += 1
        return (44 if calls < 5 else 45, len(data), 512)
    changed_output = base / 'changed'
    try:
        run(changed_output, identity=changed)
        raise AssertionError('Changed card was accepted')
    except ValueError:
        assert not (changed_output / 'pipeline-report.json').exists()
    # An unfamiliar card size falls back to file decoding without obtaining raw access.
    count = len(descriptors)
    fallback = base / 'fallback'
    assert run(fallback, size=len(data) + 512) == 2
    assert len(descriptors) == count
    assert json.loads((fallback / 'pipeline-report.json').read_text())['quality_counts'] == {
        'full_resolution_copy': 1, 'manual_review': 1}
    # Metadata mismatch must also use folder recovery, never apply another card's recipe.
    card.write_bytes(b'X' + bytes(data[1:]))
    mismatch = base / 'mismatch'
    assert run(mismatch) == 2
    assert not (mismatch / 'best_available/test.jpg').exists()
    assert photo.read_bytes() == jpeg and unknown.read_bytes() == b'not a jpeg'
    assert card.read_bytes() == b'X' + bytes(data[1:])
    for fd in descriptors:
        try:
            os.fstat(fd)
            raise AssertionError('Source descriptor leaked')
        except OSError:
            pass
print('Selective card checks passed: verified original, bounded reads, fallback, changed source and conflicts.')
