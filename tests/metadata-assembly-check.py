#!/usr/bin/env python3
import hashlib,importlib,io,json,sys,tempfile
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
assembly=importlib.import_module('assemble-metadata')
scan=importlib.import_module('scan-images')

def jpeg(image,exif=None):
    out=io.BytesIO();image.save(out,format='JPEG',quality=95,**({'exif':exif} if exif else {}));return out.getvalue()

def picture(size):
    image=Image.new('RGB',size,'navy')
    image.paste('orange',(0,0,size[0]//2,size[1]//2));return image

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);best=root/'best_available';best.mkdir()
    thumb=picture((160,120));thumb.paste(picture((160,107)),(0,6))
    exif=Image.Exif();exif[271]='Canon';exif[272]='Fixture';exif[274]=8
    exif[34665]={40962:3000,40963:2000,36867:'2026:10:10 12:00:00'}
    with Image.open(io.BytesIO(jpeg(picture((3000,2000)),exif))) as donor:
        metadata=assembly.preview_exif(donor,(3000,2000),thumb)
    primary=assembly.replace_exif(jpeg(picture((3000,2000))),metadata)
    preview=jpeg(picture((1620,1080)))
    rows=[]
    for offset,data,quality,size in [(512,primary,'full_resolution_copy',[3000,2000]),(5000000,preview,'carved_jpeg',[1620,1080])]:
        path=best/f'Photo-{offset:012x}.JPG';path.write_bytes(data)
        rows.append({'offset':offset,'output':str(path),'quality':quality,'dimensions':size,'sha256':hashlib.sha256(data).hexdigest()})
    report=root/'pipeline-report.json';report.write_text(json.dumps({'complete':True,'method':'contiguous_jpeg_carving_v1','photos':rows}))
    groups=assembly.assemble(report);assert len(groups)==1
    repaired=Path(groups[0]['metadata_copy']).read_bytes()
    assert assembly.replace_exif(repaired)==assembly.replace_exif(preview)
    with Image.open(io.BytesIO(repaired)) as photo:
        photo.load();tags=photo.getexif();assert tags[274]==8 and photo.size==(1620,1080)
        frame=tags.get_ifd(34665);assert frame[40962]==1620 and frame[40963]==1080
        assert frame[36867]=='2026:10:10 12:00:00'
        assert scan.embedded_thumbnail(photo.info['exif']) is not None
    assert Path(rows[0]['output']).read_bytes()==primary and Path(rows[1]['output']).read_bytes()==preview
    before=Path(groups[0]['metadata_copy']).stat().st_mtime_ns
    assert len(assembly.assemble(report))==1 and Path(groups[0]['metadata_copy']).stat().st_mtime_ns==before
    # Conflicting existing camera metadata must override visual similarity.
    wrong = Image.Exif(); wrong[271] = 'Different camera'
    conflicting = jpeg(picture((1620,1080)), wrong)
    Path(rows[1]['output']).write_bytes(conflicting)
    rows[1]['sha256'] = hashlib.sha256(conflicting).hexdigest()
    report.write_text(json.dumps({'complete':True,'method':'contiguous_jpeg_carving_v1','photos':rows}))
    assert assembly.assemble(report) == []
    Path(rows[1]['output']).write_bytes(preview)
    rows[1]['sha256'] = hashlib.sha256(preview).hexdigest()
    # Two indistinguishable donors must not assign metadata arbitrarily.
    duplicate=best/'Photo-000000000400.JPG';duplicate.write_bytes(primary)
    rows.append(dict(rows[0],offset=1024,output=str(duplicate)))
    report.write_text(json.dumps({'complete':True,'method':'contiguous_jpeg_carving_v1','photos':rows}))
    assert assembly.assemble(report)==[]
    # A changed preview is refused before a derivative can be overwritten.
    rows.pop();Path(rows[1]['output']).write_bytes(preview+b'changed')
    report.write_text(json.dumps({'complete':True,'method':'contiguous_jpeg_carving_v1','photos':rows}))
    try:assembly.assemble(report);raise AssertionError('Changed source accepted')
    except ValueError:pass
print('Metadata pairing checks passed: unambiguous matching, EXIF orientation/date/dimensions, embedded thumbnail, unchanged image stream, original preservation, idempotence and changed-source refusal.')
