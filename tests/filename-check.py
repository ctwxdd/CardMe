#!/usr/bin/env python3
"""Naming preserves JPEG bytes, collisions, path safety and interrupted resumes."""
import hashlib, importlib, io, sys, tempfile
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
carve = importlib.import_module('carve-photos')
with tempfile.TemporaryDirectory() as tmp:
    best = Path(tmp)
    def row(offset, name=None, date=None):
        exif = Image.Exif()
        if date is not None:
            exif[34665] = {36867: date}
        stream = io.BytesIO()
        Image.new('RGB', (32, 32), 'blue').save(stream, format='JPEG', exif=exif)
        path = best / f'Photo-{offset:012x}.JPG'
        path.write_bytes(stream.getvalue())
        result = dict(offset=offset, path=path.name, output=str(path), sha256=hashlib.sha256(stream.getvalue()).hexdigest())
        if name is not None:
            result['original_filename_hint'] = name
        return result
    rows = [row(1, 'IMG_0001.JPG', '2026:10:07 14:30:25'),
            row(2, date='2026:10:07 14:30:25'), row(3, date='2026:10:07 14:30:25'),
            row(4, '../escape.JPG', '2026:10:07 14:30:26'), row(5, date='bad date'),
            row(6, 'occupied.JPG'), row(7, 'redirect.JPG'), row(8, 'img_0001.jpg')]
    (best / 'occupied.JPG').write_bytes(b'keep')
    (best / 'redirect.JPG').symlink_to(best / 'occupied.JPG')
    state = {'photos': rows}
    carve.restore_names(state, best, lambda: None)
    assert rows[0]['path'] == 'IMG_0001.JPG' and rows[0]['filename_origin'] == 'directory_entry'
    assert rows[1]['path'] == '20261007_143025.JPG' and rows[1]['filename_origin'] == 'exif_datetime'
    assert rows[2]['path'] == '20261007_143025-000000000003.JPG'
    assert rows[3]['path'] == '20261007_143026.JPG'
    assert rows[4]['path'] == 'Photo-000000000005.JPG'
    assert rows[5]['path'] == 'occupied-000000000006.JPG'
    assert rows[6]['path'] == 'redirect-000000000007.JPG'
    assert rows[7]['path'] == 'img_0001-000000000008.jpg'
    assert (best / 'occupied.JPG').read_bytes() == b'keep' and (best / 'redirect.JPG').is_symlink()
    for saved in rows:
        assert hashlib.sha256(Path(saved['output']).read_bytes()).hexdigest() == saved['sha256']
    before = {p.name for p in best.iterdir()}
    carve.restore_names(state, best, lambda: None)
    assert before == {p.name for p in best.iterdir()}
    interrupted = row(9, 'IMG_0009.JPG')
    original = dict(interrupted)
    def stop(): raise KeyboardInterrupt
    try: carve.restore_names({'photos': [interrupted]}, best, stop)
    except KeyboardInterrupt: pass
    # Last persisted checkpoint still has the old path; the existing link is reused.
    carve.restore_names({'photos': [original]}, best, lambda: None)
    assert original['path'] == 'IMG_0009.JPG' and not (best / 'Photo-000000000009.JPG').exists()
print('Filename reconstruction checked: directory priority, EXIF dates, byte identity, collisions, symlinks and resume.')
