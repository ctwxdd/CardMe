#!/usr/bin/env python3
"""Preview-guided four-fragment recovery and fail-closed source safety."""
import hashlib, importlib, io, json, os, runpy, tempfile, time
from pathlib import Path
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[1]
# Reuse the real MPF/EXIF camera fixture and run its existing causal regressions.
fixture = runpy.run_path(str(root / 'tests/fragment-carving-check.py'))
guided = importlib.import_module('preview-guided')
guided.native.ROOT = Path(os.environ.get('CARDME_NATIVE_ENGINE', root / 'engine'))
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
        payload[at + end - first:at + end - first + 16] = b'\xff\xd8' + bytes(14)
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
        native_started = time.monotonic()
        result, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        native_seconds = time.monotonic() - native_started
        assert result, reason
        assert result['data'] == primary and result['source_extents'] == expected, result['source_extents']
        assert result['manual_review'] and result['reconstruction'] == 'mpf_preview_guided'
        # Normal supplies a sector-aligned reader; the shared search must not reread the raw fd natively.
        with patch.object(guided.native, 'feed', side_effect=AssertionError('Unaligned native raw-card read')):
            supplied, supplied_reason = guided.reconstruct(None, len(payload), candidate, [row], cluster, heap,
                lambda: None, pread=lambda _, n, p: bytes(payload[p:p+n]))
        assert supplied and supplied['data'] == result['data'] and supplied['source_extents'] == expected, supplied_reason
        python_started = time.monotonic()
        with patch.object(guided.native, 'ROOT', folder / 'missing-native'):
            plain, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert plain and plain['data'] == result['data'] and plain['continuation_decisions'] == result['continuation_decisions'], reason
        print('Local ranking parity timing:', {'python_seconds': time.monotonic()-python_started,
                                               'native_seconds': native_seconds}, flush=True)
        # An overshot marker cut must roll back without changing the supplied diagnostic.
        candidate['_failure_prefixes'] = [(start, cuts[1] + cluster + 2)]
        with patch.object(guided, 'LOCAL_CLUSTERS', 80):
            rolled, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert rolled and rolled['data'] == primary, reason
        assert rolled['source_extents'] == expected and rolled['prefix_rollback_clusters'] == 1
        assert candidate['_failure_prefixes'] == [(start, cuts[1] + cluster + 2)]
        # A delayed marker may lie past the MPF primary length; observe only that primary.
        candidate['_failure_prefixes'] = [(start, len(primary) + cluster * 2)]
        with patch.object(guided, 'LOCAL_CLUSTERS', 80):
            bounded, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert bounded and bounded['data'] == primary, reason
        assert bounded['prefix_hypothesis_bytes'] == cuts[1]
        candidate['_failure_prefixes'] = [(start, cuts[1] + 2)]
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

# A distant middle run is near the preview anchor, beyond the header's local window.
positions = [start, heap + cluster * 1720, heap + cluster * 1800, heap + cluster * 2048]
child = positions[-1] + fixture['logical'] - cuts[-2]
payload = bytearray(child + len(preview) + cluster)
expected = []
for first, end, at in zip(cuts, cuts[1:], positions):
    payload[at:at + end - first] = primary[first:end]
    expected.append({'offset': at, 'bytes': end - first})
    if end < len(primary):
        payload[at + end - first:at + end - first + 16] = b'\xff\xd8' + bytes(14)
payload[child:child + len(preview)] = preview
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory); source = folder / 'card.img'; source.write_bytes(payload); source.chmod(0o444)
    output = folder / 'preview.JPG'; output.write_bytes(preview)
    fd = os.open(source, os.O_RDONLY)
    try:
        candidate = fragments.header(fd, start, len(payload))
        candidate['_failure_prefixes'] = [(start, cuts[1] + 2)]
        row = {'offset': child, 'bytes': len(preview), 'output': str(output)}
        with patch.object(guided, 'EXPANDED_CLUSTERS', 0):
            assert guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)[0] is None
        result, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert result and result['data'] == primary, reason
        assert result['source_extents'] == expected and result['manual_review']
    finally: os.close(fd)
    assert source.read_bytes() == payload

# Heavily fragmented photos must finish after the shorter ranking-probe transition.
clusters = len(primary) // cluster
cut_clusters = [8] + [8 + (clusters - 8) * n // 14 for n in range(1, 14)]
cuts = [0] + [n * cluster for n in cut_clusters] + [len(primary)]
assert len(set(cuts)) == 16
positions = [start] + [heap + cluster * (90 + n * 8) for n in range(14)]
child = positions[-1] + fixture['logical'] - cuts[-2]
payload = bytearray(child + len(preview) + cluster)
# Other allocation clusters start unrelated files rather than plausible zero entropy.
for at in range(heap, len(payload) - 2, cluster):
    payload[at:at + 2] = b'\xff\xd8'
expected = []
for first, end, at in zip(cuts, cuts[1:], positions):
    payload[at:at + end - first] = primary[first:end]
    expected.append({'offset': at, 'bytes': end - first})
    if end < len(primary):
        payload[at + end - first:at + end - first + 16] = b'\xff\xd8' + bytes(14)
payload[child:child + len(preview)] = preview
with tempfile.TemporaryDirectory() as directory:
    folder = Path(directory); source = folder / 'card.img'; source.write_bytes(payload); source.chmod(0o444)
    output = folder / 'preview.JPG'; output.write_bytes(preview)
    fd = os.open(source, os.O_RDONLY)
    try:
        candidate = fragments.header(fd, start, len(payload))
        candidate['_failure_prefixes'] = [(start, cuts[1] + 2)]
        row = {'offset': child, 'bytes': len(preview), 'output': str(output)}
        result, reason = guided.reconstruct(fd, len(payload), candidate, [row], cluster, heap, lambda: None)
        assert result and result['data'] == primary, reason
        assert result['source_extents'] == expected and len(result['continuation_decisions']) == 14
        assert result['manual_review']
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

# All rollback attempts share the original budget; each retry cannot reset it.
clock, attempts = [0], []
def budget_trial(fd, total, candidate, photos, cluster, heap, verify, adaptive_prefix=False, pread=None):
    verify()
    attempts.append(adaptive_prefix)
    clock[0] += 60
    return None, 'invalid_preview_guided_prefix'
budget_candidate = {'offset': 0, 'bytes': 100, '_failure_prefixes': [(0, 40)]}
with patch.object(guided.time, 'monotonic', side_effect=lambda: clock[0]), patch.object(guided, '_reconstruct', side_effect=budget_trial):
    assert guided.reconstruct(None, 100, budget_candidate, [], 10, 0, lambda: None)[1] == 'preview_guided_time_budget'
assert attempts == [False, True], attempts
for refusal in ('missing_or_ambiguous_preview', 'invalid_preview_guided_coding', 'preview_guided_join_budget'):
    with patch.object(guided, '_reconstruct', return_value=(None, refusal)) as search:
        assert guided.reconstruct(None, 100, budget_candidate, [], 10, 0, lambda: None)[1] == refusal
        assert search.call_count == 1
print('Preview-guided checks passed: exact four-part bytes, review status, ambiguous preview, budgets, cancellation, short reads, ownership, source unchanged and decoder checkpoints.')
