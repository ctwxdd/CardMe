#!/usr/bin/env python3
"""Formatted-card MPF reconstruction: exact bytes, bounded joins, ambiguity and safety."""
import hashlib, importlib, io, json, os, struct, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
carve = importlib.import_module('carve-photos')
fragments = importlib.import_module('fragment-carve')
allocation = importlib.import_module('fragment-rescue')
metadata = importlib.import_module('assemble-metadata')

for malformed, message in ((b'\xff\xd8\xff\xd8', 'Unexpected JPEG marker'),
                           (b'\xff\xd8\xff\xe0\x00\x01', 'Invalid JPEG segment length')):
    try:
        carve.jpeg_extent(None, 0, len(malformed), lambda _, size, offset: malformed[offset:offset + size])
        raise AssertionError('Malformed marker structure accepted')
    except carve.JPEGMarkerError as error:
        assert str(error) == message and error.offset > 0

def jpeg(image, exif=None):
    out = io.BytesIO(); image.save(out, format='JPEG', quality=95, **({'exif':exif} if exif else {})); return out.getvalue()

photo = Image.new('RGB', (2400,1600))
photo.putdata([(x*255//2400, y*255//1600, (x+y)*255//4000) for y in range(1600) for x in range(2400)])
preview = jpeg(photo.resize((1620,1080)))
exif = Image.Exif(); exif[271] = 'Canon'; exif[272] = 'Fixture'; exif[274] = 8
exif[34665] = {40962:2400, 40963:1600, 36867:'2026:10:10 12:00:00'}
with Image.open(io.BytesIO(jpeg(photo,exif))) as donor:
    tags = metadata.preview_exif(donor, photo.size, photo.resize((160,107)))
plain = metadata.replace_exif(jpeg(photo), tags)
length = len(plain) + 90; logical = length + 128
mpf = b'II*\0'+struct.pack('<IH',8,3)
mpf += struct.pack('<HHI',0xB000,7,4)+b'0100'
mpf += struct.pack('<HHII',0xB001,4,1,2)+struct.pack('<HHII',0xB002,7,32,50)+bytes(4)
mpf += struct.pack('<IIIHH',0x80030000,length,0,2,0)
mpf += struct.pack('<IIIHH',0x40010002,len(preview),logical-10,0,0)
primary = plain[:2]+b'\xff\xe2'+struct.pack('>H',len(mpf)+6)+b'MPF\0'+mpf+plain[2:]
assert len(primary) == length
cluster,heap = 4096,5120
start = heap+cluster*4; cut=cluster*8; suffix=heap+cluster*1024
child = suffix+logical-cut
payload=bytearray(child+len(preview)+cluster)
payload[start:start+cut]=primary[:cut]
payload[start+cut:start+cut+20]=b'\xff\xd8\xff\xe1'+bytes(16)
payload[suffix:suffix+length-cut]=primary[cut:]
payload[child:child+len(preview)]=preview
sha=lambda b:hashlib.sha256(b).hexdigest()
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); folder=root/'Card Safety Copy test'; folder.mkdir(); source=folder/'card.img'; source.write_bytes(payload); source.chmod(0o444)
    output=root/'results'; geometry=(0,None,512,cluster,heap,2048,2,b'')
    with patch.object(allocation,'volume',return_value=geometry):
        assert carve.recover(source,output)==0
    report=json.loads((output/'pipeline-report.json').read_text())
    rebuilt=[r for r in report['photos'] if r['quality']=='full_resolution_reconstructed'];assert len(rebuilt)==1,report['fragment_analysis']
    row=rebuilt[0];assert Path(row['output']).read_bytes()==primary
    assert row['source_extents']==[{'offset':start,'bytes':cut},{'offset':suffix,'bytes':length-cut}]
    assert row['byte_exact_source_fragments'] and not row['byte_exact_source_copy'] and row['review_required']
    assert report['fragment_analysis']['candidates'][str(start)]['reason']=='reconstructed'
    assert sha(source.read_bytes())==sha(payload)
    groups=json.loads((output/'metadata-assembly.json').read_text())['groups']
    assert any(g['primary_offset']==start and g['preview_offset']==child and g['comparison']=='mpf_index' for g in groups),groups
    # An indexed preview may rescue bytes while a disagreeing thumbnail keeps review status.
    review_output = root/'review-results'
    with patch.object(allocation,'volume',return_value=geometry), patch.object(fragments.scan,'embedded_thumbnail',return_value=Image.new('RGB',(160,107),'green')):
        assert carve.recover(source,review_output)==2
    reviewed = json.loads((review_output/'pipeline-report.json').read_text())
    review_row = next(r for r in reviewed['photos'] if r.get('reconstruction'))
    assert review_row['quality']=='manual_review' and review_row['review_required']
    assert Path(review_row['output']).read_bytes()==primary
    before=Path(row['output']).stat().st_mtime_ns
    with patch.object(fragments,'reconstruct',side_effect=AssertionError('Completed joins were retried')):
        assert carve.recover(source,output)==0
    assert Path(row['output']).stat().st_mtime_ns==before
    fd=os.open(source,os.O_RDONLY)
    try:
        candidate=fragments.header(fd,start,len(payload));assert candidate
        preview_row=next(r for r in report['photos'] if r['offset']==child)
        assert fragments.reconstruct(fd,len(payload),candidate,[preview_row,preview_row],cluster,heap,lambda:None)[1]=='missing_or_ambiguous_preview'
        bad_thumbnail = dict(candidate, thumbnail=Image.new('RGB',(160,107),'green'))
        matched, reason = fragments.reconstruct(fd,len(payload),bad_thumbnail,[preview_row],cluster,heap,lambda:None)
        assert reason == 'reconstructed' and matched['data'] == primary and matched['thumbnail_difference'] > 5
        assert matched['preview_difference'] < 3
        def cancel():raise KeyboardInterrupt
        try:fragments.reconstruct(fd,len(payload),candidate,[preview_row],cluster,heap,cancel);raise AssertionError('Cancellation ignored')
        except KeyboardInterrupt:pass
        with patch.object(fragments,'MAX_BOUNDARIES',1):
            assert fragments.reconstruct(fd,len(payload),candidate,[preview_row],cluster,heap,lambda:None)[1]=='fragment_search_budget'
        with patch.object(fragments.os,'pread',return_value=b''):
            try:fragments.header(fd,start,len(payload));raise AssertionError('Short source read accepted')
            except OSError:pass
    finally:os.close(fd)
    Path(row['output']).write_bytes(b'keep me')
    try:carve.recover(source,output);raise AssertionError('Changed output overwritten')
    except ValueError:pass
    assert Path(row['output']).read_bytes()==b'keep me'
print('Fragment carving checks passed: exact source extents, automatic handoff, MPF metadata, resume, ambiguity, cancellation, budgets and no overwrite.')

# A synthetic causal three-extent fixture: the first marker failure only suggests
# the prefix length; an occupied cluster separates that prefix from a free middle gap.
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); source = root / 'three.img'
    boundary = cluster * 10
    three_suffix = heap + cluster * 100
    three_child = three_suffix + logical - boundary
    three_payload = bytearray(three_child + len(preview) + cluster)
    three_start = heap + cluster * 4
    three_cut = cluster * 8
    middle_start = three_start + three_cut + cluster * 8
    three_payload[three_start:three_start + three_cut] = primary[:three_cut]
    three_payload[three_start + three_cut:three_start + three_cut + cluster * 4] = b'X' * (cluster * 4)
    three_payload[middle_start:middle_start + boundary - three_cut] = primary[three_cut:boundary]
    three_payload[three_suffix:three_suffix + len(primary) - boundary] = primary[boundary:]
    three_payload[three_child:three_child + len(preview)] = preview
    source.write_bytes(three_payload)
    fd = os.open(source, os.O_RDONLY)
    try:
        three_candidate = fragments.header(fd, three_start, len(three_payload))
        assert three_candidate
        preview_path = root / 'preview.jpg'; preview_path.write_bytes(preview)
        preview_row = {'offset': three_child, 'bytes': len(preview), 'output': str(preview_path)}
        three_candidate['_known_photos'] = [
            {'offset': three_start + three_cut, 'bytes': cluster * 4},
            {'offset': three_suffix - cluster, 'bytes': cluster}]
        jpeg_extent = carve.jpeg_extent
        def failed_marker(source_fd, source_start, source_total, pread=None):
            if source_fd == fd and source_start == three_start:
                raise carve.JPEGMarkerBoundaryError(three_cut)
            return jpeg_extent(source_fd, source_start, source_total, pread)
        with patch.object(carve, 'jpeg_extent', side_effect=failed_marker):
            rebuilt = fragments.reconstruct_three(fd, len(three_payload), three_candidate,
                                                  [preview_row], cluster, heap, lambda: None)
        assert rebuilt and rebuilt['data'] == primary
        assert rebuilt['source_extents'] == [
            {'offset': three_start, 'bytes': three_cut},
            {'offset': middle_start, 'bytes': boundary - three_cut},
            {'offset': three_suffix, 'bytes': len(primary) - boundary}]
        retry_state = {'fragment_candidates': [three_start], 'photos': [],
                       'fragment_analysis': {'candidates': {str(three_start): {
                           'reason': 'no_valid_two_extent_join', 'algorithm_version': 1}}}}
        header_row = {'offset': three_start, 'bytes': len(primary), 'thumbnail': None,
                      'preview_logical': logical, 'preview_bytes': len(preview)}
        with patch.object(allocation, 'volume', return_value=geometry), \
             patch.object(carve, 'jpeg_extent', side_effect=carve.JPEGMarkerError('Unexpected JPEG marker', three_cut)) as probe, \
             patch.object(fragments, 'header', return_value=header_row), \
             patch.object(fragments, 'reconstruct', return_value=(None, 'no_valid_two_extent_join')):
            fragments.recover(fd, len(three_payload), retry_state, root, lambda: None, lambda: None)
            assert retry_state['fragment_analysis']['candidates'][str(three_start)]['algorithm_version'] == 2
            assert probe.call_count == 1
        with patch.object(allocation, 'volume', return_value=geometry), \
             patch.object(carve, 'jpeg_extent', side_effect=AssertionError('Completed candidate was reprobed')) as probe, \
             patch.object(fragments, 'header', side_effect=AssertionError('Completed candidate was retried')):
            fragments.recover(fd, len(three_payload), retry_state, root, lambda: None, lambda: None)
            probe.assert_not_called()
        def cancel_three(): raise KeyboardInterrupt
        with patch.object(carve, 'jpeg_extent', side_effect=failed_marker):
            try:
                fragments.reconstruct_three(fd, len(three_payload), three_candidate,
                                            [preview_row], cluster, heap, cancel_three)
                raise AssertionError('Three-extent cancellation ignored')
            except KeyboardInterrupt:
                pass
            with patch.object(fragments.os, 'pread', return_value=b''):
                try:
                    fragments.reconstruct_three(fd, len(three_payload), three_candidate,
                                                [preview_row], cluster, heap, lambda: None)
                    raise AssertionError('Short three-extent source read accepted')
                except OSError:
                    pass
    finally:
        os.close(fd)

# The recovery flow must first rebuild a fragmented indexed preview from scan
# endpoint hints, then use that saved preview to validate the primary join.
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary); source = root / 'fragmented-preview.img'
    child = suffix + logical - cut
    preview_cut = cluster - (child - heap) % cluster
    preview_within = (child - heap + len(preview)) % cluster
    preview_end = heap + preview_within + cluster * 1200
    preview_suffix = preview_end - (len(preview) - preview_cut)
    payload = bytearray(preview_end + cluster)
    payload[start:start + cut] = primary[:cut]
    payload[start + cut:start + cut + 20] = b'\xff\xd8\xff\xe1' + bytes(16)
    payload[suffix:suffix + len(primary) - cut] = primary[cut:]
    payload[child:child + preview_cut] = preview[:preview_cut]
    payload[child + preview_cut:child + preview_cut + 3] = b'\xff\xd8\xff'
    payload[preview_suffix:preview_end] = preview[preview_cut:]
    source.write_bytes(payload); source.chmod(0o444)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = root / 'recovery'
    with patch.object(allocation, 'volume', return_value=geometry):
        assert carve.recover(source, output) == 0
    report = json.loads((output / 'pipeline-report.json').read_text())
    preview_row = next(row for row in report['photos'] if row.get('reconstruction') == 'mpf_preview_two_extent')
    primary_row = next(row for row in report['photos'] if row.get('reconstruction') == 'mpf_two_extent')
    assert Path(preview_row['output']).read_bytes() == preview
    assert preview_row['quality'] == 'camera_preview' and preview_row['review_required']
    assert preview_row['source_extents'] == [
        {'offset': child, 'bytes': preview_cut},
        {'offset': preview_suffix, 'bytes': len(preview) - preview_cut}]
    assert Path(primary_row['output']).read_bytes() == primary
    assert primary_row['paired_preview_offset'] == child
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_digest

# Extreme but volume-bounded frame dimensions must not allocate an oversized comparison.
assert fragments.comparison_size([1, 64_000_000]) == (1, 512)
assert fragments.comparison_size([64_000_000, 1]) == (512, 1)
assert fragments.comparison_size([6240, 4160]) == (512, 341)
