import importlib,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
engine=importlib.import_module('orphan-entries')
def entry(name='IMG_1234.JPG'):
 data=bytearray(96);data[0]=0x85;data[1]=2;data[4]=32;data[32:36]=bytes((0xc0,1,0,len(name)))
 struct.pack_into('<Q',data,40,65536);struct.pack_into('<I',data,52,5);struct.pack_into('<Q',data,56,65536)
 data[64]=0xc1;data[66:66+len(name)*2]=name.encode('utf-16-le')
 checksum=0
 for i,v in enumerate(data):
  if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+v)&65535
 struct.pack_into('<H',data,2,checksum);return data
raw=entry();rows=engine.collect(bytes(32)+raw+bytes(64),4096,4096,131072,100)
assert len(rows)==1 and rows[0]['original_filename_hint']=='IMG_1234.JPG' and rows[0]['offset']==397312
assert engine.collect(raw,4097,4096,131072,100)==[]
bad=raw.copy();bad[66]^=1;assert engine.collect(bad,4096,4096,131072,100)==[]
assert engine.collect(entry('../bad.JPG'),4096,4096,131072,100)==[]
assert engine.collect(raw[:90],4096,4096,131072,100)==[]
assert engine.collect(raw,4096,4096,131072,2)==[]
extra=raw.copy()+bytes(32);extra[1]=3;extra[96]=0xc1
checksum=0
for i,v in enumerate(extra):
 if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+v)&65535
struct.pack_into('<H',extra,2,checksum)
assert engine.collect(extra,4096,4096,131072,100)==[]
print('Orphan entry hints checked: checksum, alignment, source bounds, safe filename and truncation.')

# The regular scan retains an entry crossing its chunk boundary, without a second scan.
import hashlib,io,json,tempfile
from unittest.mock import patch
from PIL import Image
carve=importlib.import_module('carve-photos')
volume=importlib.import_module('fragment-rescue')
with tempfile.TemporaryDirectory() as temporary:
 root=Path(temporary);image=root/'card.img';output=root/'saved'
 photo=io.BytesIO();Image.new('RGB',(640,480),'blue').save(photo,format='JPEG')
 payload=bytearray(65536);payload[32768:32768+len(photo.getvalue())]=photo.getvalue()
 metadata=entry();struct.pack_into('<Q',metadata,40,len(photo.getvalue()));struct.pack_into('<I',metadata,52,10);struct.pack_into('<Q',metadata,56,len(photo.getvalue()))
 checksum=0
 for i,v in enumerate(metadata):
  if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+v)&65535
 struct.pack_into('<H',metadata,2,checksum)
 payload[4064:4160]=metadata
 image.write_bytes(payload);image.chmod(0o444);before=hashlib.sha256(payload).hexdigest()
 with patch.object(carve,'CHUNK',4096),patch.object(volume,'volume',return_value=(0,512,0,4096,0,16)),patch.object(importlib.import_module('fragment-carve'),'recover'):
  assert carve.recover(image,output)==0
 report=json.loads((output/'pipeline-report.json').read_text())
 assert report['photos'][0]['original_filename_hint']=='IMG_1234.JPG'
 assert report['photos'][0]['directory_entry_offsets']==[4064]
 assert report['photos'][0]['path']=='IMG_1234.JPG'
 assert Path(report['photos'][0]['output']).read_bytes()==photo.getvalue()
 with patch.object(volume,'volume',return_value=(0,512,0,4096,0,16)),patch.object(importlib.import_module('fragment-carve'),'recover'):
  assert carve.recover(image,output)==0
 assert len(list((output/'best_available').glob('*.JPG')))==1
 assert hashlib.sha256(image.read_bytes()).hexdigest()==before
print('Orphan metadata retained by the regular scan across a chunk boundary, source unchanged.')
