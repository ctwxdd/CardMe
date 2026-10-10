#!/usr/bin/env python3
"""Formatted-card fixture: exact JPEGs, marker boundaries, pause/resume and read-only safety."""
import ctypes, hashlib, importlib, io, json, os, subprocess, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
carve = importlib.import_module('carve-photos')
safety = importlib.import_module('safety')
sha = lambda value: hashlib.sha256(value).hexdigest()

def jpeg(size, color, **options):
    out = io.BytesIO(); Image.new('RGB', size, color).save(out, format='JPEG', **options)
    return out.getvalue()

with tempfile.TemporaryDirectory(prefix='cardrescue-carving-') as temporary:
    root = Path(temporary); output = root / 'results'
    safety_folder = root / 'Card Safety Copy fixture'
    safety_folder.mkdir()
    image = safety_folder / 'card.img'
    # No usable filesystem directory, FAT, filename or matching card profile remains.
    payload = bytearray(128 * 1024)
    preview = jpeg((160, 120), 'red')
    # A valid JPEG nested in an APP segment must not truncate or become a second photo.
    app = b'\xff\xe2' + (len(preview) + 2).to_bytes(2, 'big') + preview
    first = jpeg((640, 480), 'red', quality=95)
    first = first[:2] + app + first[2:]
    second = jpeg((480, 640), 'blue', progressive=True)
    thumb = jpeg((160, 120), 'yellow')
    offsets = [4094, 24000, 70000] # First SOI straddles the chunk boundary.
    originals = dict(zip(offsets, (first, second, thumb)))
    for offset, data in originals.items(): payload[offset:offset+len(data)] = data
    payload[18000:18006] = b'\xff\xd8\xff\xe1\xff\xff' # Invalid/truncated candidate, followed by a valid photo.
    broken = jpeg((640, 480), 'green')[:-2]
    payload[90000:90000+len(broken)] = broken
    image.write_bytes(payload); image.chmod(0o444)
    source_hash = sha(image.read_bytes())
    with patch.object(carve, 'CHUNK', 4096):
        assert carve.recover(image, output) == 0
    report = json.loads((output / 'pipeline-report.json').read_text())
    assert report['complete'] and report['next_offset'] == len(payload)
    assert report['quality_counts'] == {'carved_jpeg': 2, 'thumbnail_only': 1}
    assert len(report['photos']) == 3
    for row in report['photos']:
        assert Path(row['output']).read_bytes() == originals[row['offset']]
        assert row['byte_exact_source_copy'] and row['sha256'] == sha(originals[row['offset']])
    assert sha(image.read_bytes()) == source_hash
    # Native volume rejection is enforced by the engine, not just the Swift picker.
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    restricted = SimpleNamespace(_handle=cf._handle,
        CFURLCreateFromFileSystemRepresentation=cf.CFURLCreateFromFileSystemRepresentation,
        CFURLCopyResourcePropertyForKey=cf.CFURLCopyResourcePropertyForKey,
        CFBooleanGetValue=lambda _: True, CFRelease=cf.CFRelease)
    with patch.object(safety.ctypes, 'CDLL', return_value=restricted):
        try: carve.recover(image, root/'forbidden-volume'); raise AssertionError('Restricted volume accepted')
        except ValueError: pass
    assert not (root/'forbidden-volume').exists()
    # A completed resume must preserve all outputs without duplicates.
    before = {p: p.stat().st_mtime_ns for p in (output / 'best_available').iterdir()}
    assert carve.recover(image, output) == 0
    assert before == {p: p.stat().st_mtime_ns for p in before}
    # Stop after publishing a photo but before a chunk checkpoint. Resume rediscovers it safely.
    paused = root / 'paused'; publish = carve.save_exact
    calls = 0
    def interrupt_after_first(target, data):
        global calls
        result = publish(target, data); calls += 1
        if calls == 1: raise KeyboardInterrupt
        return result
    with patch.object(carve, 'save_exact', side_effect=interrupt_after_first):
        try: carve.recover(image, paused); raise AssertionError('Cancellation ignored')
        except KeyboardInterrupt: pass
    partial = json.loads((paused / 'pipeline-report.json').read_text())
    assert not partial['complete'] and len(list((paused / 'best_available').iterdir())) == 1
    assert carve.recover(image, paused) == 0
    assert len(json.loads((paused / 'pipeline-report.json').read_text())['photos']) == 3
    assert sha(image.read_bytes()) == source_hash
    # Conflicting outputs must stay intact, and must stop recovery rather than overwrite.
    target = next((paused / 'best_available').iterdir()); target.write_bytes(b'keep-me')
    try: carve.recover(image, paused); raise AssertionError('Conflict accepted')
    except ValueError: pass
    assert target.read_bytes() == b'keep-me'
    # Identity changes invalidate the checkpoint before reusing results.
    image.chmod(0o644); image.write_bytes(bytes(payload[:-1]) + b'X')
    try: carve.recover(image, output); raise AssertionError('Changed image accepted')
    except ValueError: pass
    image.write_bytes(payload)
    # Refuse output in a source ancestor and redirected result directories.
    try: carve.recover(image, root); raise AssertionError('Source ancestor accepted')
    except ValueError: pass
    redirected = root / 'redirected'; redirected.mkdir()
    (redirected / 'best_available').symlink_to(root)
    try: carve.recover(image, redirected); raise AssertionError('Redirected output accepted')
    except ValueError: pass
    # An I/O error while parsing must stop safely; it is not a rejected JPEG.
    pread = os.pread
    def failed_read(fd, count, offset):
        if offset == offsets[0]: raise OSError('Simulated source read failure')
        return pread(fd, count, offset)
    with patch.object(carve.os, 'pread', side_effect=failed_read):
        try: carve.recover(image, root / 'io-failure'); raise AssertionError('I/O failure swallowed')
        except OSError: pass
    # Oversized SOF dimensions are rejected before pixel allocation.
    unsafe = b'\xff\xd8\xff\xc0\x00\x0b\x08\xff\xff\xff\xff\x01\x01\x11\x00\xff\xd9'
    huge = root / 'huge.img'; huge.write_bytes(unsafe + bytes(512))
    with huge.open('rb') as f:
        try: carve.jpeg_extent(f.fileno(), 0, huge.stat().st_size); raise AssertionError('Unsafe dimensions accepted')
        except ValueError: pass
    # The shipped dispatcher must fall back to general recovery for a formatted, unfamiliar card image.
    fallback = root / 'fallback'
    subprocess.run([sys.executable, '-B', str(ROOT/'engine/sd-rescue.py'), '--image', str(image), '--output', str(fallback)], check=True, stdout=subprocess.DEVNULL)
    assert len(json.loads((fallback/'pipeline-report.json').read_text())['photos']) == 3
    assert sha(image.read_bytes()) == source_hash
print('Formatted JPEG recovery checks passed: exact bytes, progressive JPEG, chunk/APP boundaries, cancellation, resume, conflicts, source identity and read-only source.')
