#!/usr/bin/env python3
"""Exercise no-image rescue, mixed failures, resume and source/destination safety."""
import importlib, json, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
root = Path(__file__).resolve().parents[1]
engine = root / 'engine'
sys.path.insert(0, str(engine))
rescue = importlib.import_module('rescue-folder')
with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp)
    source = folder / 'source'
    source.mkdir()
    original = source / 'broken.jpg'
    Image.new('RGB', (64, 48), 'red').save(original)
    data = original.read_bytes()
    bad = source / 'missing-data.jpg'
    bad.write_bytes(b'not a jpeg')
    flagged = {'path': str(original), 'status': 'decode_error', 'failed_stage': 'image', 'bytes': len(data), 'mtime_ns': original.stat().st_mtime_ns}
    report = folder / 'scan.json'
    report.write_text(json.dumps({'images': [flagged, {'path': str(bad), 'status': 'decode_error', 'bytes': bad.stat().st_size}]}))
    output = folder / 'results'
    args = ['rescue-folder.py', '--source', str(source), '--scan', str(report), '--output', str(output)]
    # Deterministic embedded thumbnail exercises the real publication path; corrupt input remains a failure.
    thumbnail = Image.new('RGB', (16, 12), 'red')
    with patch.object(rescue.scan, 'embedded_thumbnail', return_value=thumbnail), patch.object(sys, 'argv', args):
        assert rescue.main() == 2
    summary = json.loads((output / 'pipeline-report.json').read_text())
    assert summary['quality_counts'] == {'full_resolution': 1, 'manual_review': 1}
    recovered = Path(summary['photos'][0]['output'])
    assert recovered.suffix == '.jpg' and recovered.read_bytes() == data
    with Image.open(recovered) as photo:
        photo.load()
        assert photo.size == (64, 48)
    assert original.read_bytes() == data
    # Preserve camera EXIF/orientation rather than baking rotation into a re-encoded image.
    exif = Image.Exif(); exif[271] = 'Canon'; exif[274] = 8
    tagged = source / 'orientation.jpg'; Image.new('RGB',(64,48),'red').save(tagged,exif=exif)
    original_tagged = tagged.read_bytes()
    with patch.object(rescue.scan,'embedded_thumbnail',return_value=None):
        payload, kind, suffix, dims = rescue.recover_bytes(tagged, {'failed_stage':'exif'})
    assert payload == original_tagged and kind == 'full_resolution' and suffix == '.jpg' and dims == [64,48]
    with Image.open(__import__('io').BytesIO(payload)) as saved:
        assert saved.getexif()[274] == 8 and saved.getexif()[271] == 'Canon'
    # An image that can be decoded but has no complete JPEG marker extent stays a labelled PNG fallback.
    truncated = source/'no-eoi.jpg'; truncated.write_bytes(data[:-2])
    with patch.object(rescue,'recover',return_value=(Image.new('RGB',(64,48),'red'),'full_resolution_copy')):
        payload, kind, suffix, dims = rescue.recover_bytes(truncated, flagged)
    assert payload.startswith(b'\x89PNG') and kind == 'full_resolution_copy' and suffix == '.rescued.png'
    # A flagged EXIF/header issue can still have an intact primary image, with no thumbnail.
    with patch.object(rescue.scan, 'embedded_thumbnail', return_value=None):
        photo, quality = rescue.recover(original, {**flagged, 'failed_stage': 'exif'})
        assert quality == 'full_resolution_copy' and photo.size == (64, 48)
    with patch.object(rescue.scan, 'embedded_thumbnail', return_value=thumbnail), patch.object(sys, 'argv', args):
        assert rescue.main() == 2
    recovered.write_bytes(b'conflicting output')
    with patch.object(rescue.scan, 'embedded_thumbnail', return_value=thumbnail), patch.object(sys, 'argv', args):
        assert rescue.main() == 2
    assert recovered.read_bytes() == b'conflicting output'
    # Failed primary decoding must still preserve an intact small thumbnail.
    with patch.object(rescue.scan, 'embedded_thumbnail', return_value=thumbnail), patch.object(rescue.scan, 'thumbnail_difference', return_value=99):
        photo, quality = rescue.recover(original, flagged)
        assert quality == 'thumbnail_only' and photo.size == (16, 12)
    assert original.read_bytes() == data
print('Folder rescue checks passed.')
