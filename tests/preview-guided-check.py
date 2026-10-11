#!/usr/bin/env python3
"""Preview-guided four-fragment recovery and fail-closed source safety."""
import hashlib, importlib, io, json, os, runpy, tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[1]
# Reuse the real MPF/EXIF camera fixture and run its existing causal regressions.
fixture = runpy.run_path(str(root / 'tests/fragment-carving-check.py'))
guided = importlib.import_module('preview-guided')
fragments = fixture['fragments']; coding = guided.coding
primary, preview = fixture['primary'], fixture['preview']
cluster, heap, start = fixture['cluster'], fixture['heap'], fixture['start']
cuts = [0, cluster * 8, cluster * 30, cluster * 45, len(primary)]
positions = [start, heap + cluster * 90, heap + cluster * 160, heap + cluster * 220]
child = positions[-1] + fixture['logical'] - cuts[-2]
payload = bytearray(child + len(preview) + cluster)
expected = []
for first, end, at in zip(cuts, cuts[1:], positions):
    payload[at:at + end - first] = primary[first:end]
    expected.append({'offset': at, 'bytes': end - first})
    if end < len(primary):
        payload[at + end - first:at + end - first + 16] = b'SQLite format 3\0'
payload[child:child + len(preview)] = preview
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory); source = folder / 'card.img'; source.write_bytes(payload); source.chmod(0o444)
    output = folder / 'preview.JPG'; output.write_bytes(preview)
    fd = os.open(source, os.O_RDONLY)
    try:
        candidate = fragments.header(fd, start, len(payload))
        candidate['_failure_prefixes'] = [(start, cuts[1] + 2)]
        candidate['_known_photos'] = []
        row = {'offset': child, 'bytes': len(preview), 'output': str(output)}
        result, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert result, reason
        assert result['data'] == primary and result['source_extents'] == expected, result['source_extents']
        assert result['manual_review'] and result['reconstruction'] == 'mpf_preview_guided'
        assert guided.reconstruct(fd, len(payload), candidate, [row, row], cluster, heap, lambda: None)[0] is None
        with patch.object(guided, 'MAX_SECONDS', 0):
            assert guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)[1] == 'preview_guided_time_budget'
        with patch.object(guided, 'MAX_JOINS', 1):
            assert guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)[0] is None
        def cancel(): raise InterruptedError('cancelled')
        try: guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, cancel); raise AssertionError('Cancellation swallowed')
        except InterruptedError: pass
        with patch.object(guided.os, 'pread', return_value=b''):
            try: guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None); raise AssertionError('Short read accepted')
            except OSError: pass
        # A proven other primary range must block the prefix as well as continuations.
        candidate['_known_photos'] = [{'offset': positions[1], 'quality': 'full_resolution_reconstructed',
            'sha256': hashlib.sha256(primary[:cuts[1]]).hexdigest(), 'source_extents': [expected[0]]}]
        assert guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)[1] == 'occupied_prefix_hypothesis'
        candidate['_known_photos'][0]['sha256'] = '0' * 64
        try: guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None); raise AssertionError('Changed saved extents accepted')
        except ValueError: pass
        candidate['_known_photos'] = []
        original_open = Image.open
        with patch.object(guided.Image, 'open', wraps=Image.open) as opening:
            def decode_failure(value, *args, **kwargs):
                if isinstance(value, io.BytesIO):
                    raise OSError('Invalid full JPEG')
                return original_open(value, *args, **kwargs)
            opening.side_effect = decode_failure
            assert guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)[1] == 'invalid_preview_guided_frame'
        # Exercise publication through the shared Deep/saved-image caller.
        allocation = importlib.import_module('fragment-rescue')
        geometry = (0, None, 512, cluster, heap, len(payload) // cluster, 2, b'')
        saved = folder / 'saved'; saved.mkdir()
        def pipeline_state():
            return {'photos': [dict(row)], 'fragment_candidates': [start],
                    'fragment_failure_prefixes': {str(start): {'offset': cuts[1] + 2,
                    'algorithm_version': fragments.ALGORITHM_VERSION}}}
        state = pipeline_state()
        with patch.object(allocation, 'volume', return_value=geometry), patch.object(fragments, 'reconstruct', return_value=(None, 'no_valid_two_extent_join')):
            fragments.recover(fd, len(payload), state, saved, lambda: None, lambda: None)
        published = state['photos'][-1]
        assert published['quality'] == 'manual_review' and published['review_required']
        assert published['reconstruction'] == 'mpf_preview_guided'
        assert Path(published['output']).read_bytes() == primary
        with patch.object(allocation, 'volume', return_value=geometry), patch.object(guided, 'reconstruct', side_effect=AssertionError('Repeated saved result')):
            fragments.recover(fd, len(payload), state, saved, lambda: None, lambda: None)
        for refusal in ('ambiguous_fragment_joins', 'fragment_search_budget'):
            rejected = pipeline_state()
            with patch.object(allocation, 'volume', return_value=geometry), patch.object(fragments, 'reconstruct', return_value=(None, refusal)), patch.object(guided, 'reconstruct', side_effect=AssertionError('Bypassed legacy refusal')):
                fragments.recover(fd, len(payload), rejected, saved, lambda: None, lambda: None)
            assert len(rejected['photos']) == 1
    finally: os.close(fd)
    assert source.read_bytes() == payload

# State must survive arbitrary byte splits, including pending symbols/stuffing.
for width in (1, 7, 512):
    whole = coding.Decoder(primary); whole.feed(primary[whole.header_end:])
    chunked = coding.Decoder(primary)
    for pos in range(chunked.header_end, len(primary), width):
        chunked.feed(primary[pos:pos + width])
    assert chunked.eoi and chunked.signature() == whole.signature()
    cloned = chunked.clone(); cloned.predictors[1] += 1
    assert cloned.predictors != chunked.predictors
assert guided.overlaps(9, 2, [{'offset': 10, 'bytes': 2}])
assert not guided.overlaps(8, 2, [{'offset': 10, 'bytes': 2}])
print('Preview-guided checks passed: exact four-part bytes, review status, ambiguous preview, budgets, cancellation, short reads, ownership, source unchanged and decoder checkpoints.')
