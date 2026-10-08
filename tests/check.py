#!/usr/bin/env python3
"""One runnable check: scanner, ranking and safety gates."""
import importlib, json, os, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'engine'
sys.path.insert(0, str(ENGINE))
scan = importlib.import_module('scan-images')
decisions = importlib.import_module('decision-model')
safety = importlib.import_module('safety')
scan.self_test()
decisions.self_test()
with tempfile.TemporaryDirectory(prefix='cardrescue-check-') as temporary:
    folder = Path(temporary)
    source = folder / 'source'
    source.mkdir()
    for destination in [source, source / 'results']:
        try:
            safety.validate_output(source, destination)
        except ValueError:
            pass
        else:
            raise AssertionError('Source-tree writes were accepted.')
    try:
        safety.validate_output(source, Path('/Volumes/Untitled/CardRescue-output'))
    except ValueError:
        pass
    else:
        raise AssertionError('Camera-media output was accepted.')
    # A truncated saved image must be rejected before creating recovery outputs.
    bad_image = folder / 'wrong.img'
    bad_image.write_bytes(b'not a card')
    result = subprocess.run([sys.executable, '-B', str(ENGINE / 'sd-rescue.py'), '--image', str(bad_image), '--output', str(folder / 'results')], capture_output=True, text=True)
    assert result.returncode == 1 and 'too small' in result.stderr, result.stderr
    assert not (folder / 'results').exists()
    # Generic scanner actually runs and never alters its input.
    from PIL import Image
    photo = source / 'valid.jpg'
    Image.new('RGB', (32, 24), 'red').save(photo)
    original = photo.read_bytes()
    hidden = source / '.Spotlight-V100'
    hidden.mkdir()
    (hidden / 'ignored.jpg').write_bytes(b'not a photo')
    scan_run = subprocess.run([sys.executable, '-B', str(ENGINE / 'scan-images.py'), str(source), '--report', str(folder / 'scan.json')], check=True, capture_output=True, text=True)
    assert 'SCANNING\t{"checked": 1}' in scan_run.stdout
    assert json.loads((folder / 'scan.json').read_text())['counts'] == {'ok_image_header': 1}
    assert photo.read_bytes() == original
    # A denied photo subfolder must be reported without losing the valid results.
    def denied_walk(root, onerror, followlinks):
        onerror(PermissionError(1, 'Access denied', str(source / 'denied')))
        yield str(source), [], ['valid.jpg']
    with patch.object(scan.os, 'walk', side_effect=denied_walk), patch.object(sys, 'argv', ['scan-images.py', str(source), '--report', str(folder / 'partial.json')]):
        scan.main()
    partial = json.loads((folder / 'partial.json').read_text())
    assert partial['counts'] == {'ok_image_header': 1} and len(partial['unreadable_folders']) == 1
print('All checks passed.')
