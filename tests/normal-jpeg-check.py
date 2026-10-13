"""Normal exFAT recovery uses aligned source reads and preserves the original MPO JPEG."""
import hashlib, importlib, io, json, os, runpy, struct, tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image

root = Path(__file__).resolve().parents[1]
fixture = runpy.run_path(str(root / 'tests/fragment-carving-check.py'))
normal = importlib.import_module('normal-jpeg')
allocation = importlib.import_module('fragment-rescue')
imaging = importlib.import_module('image-card')
primary, preview = fixture['primary'], fixture['preview']
cluster, heap, start, cut, child = (fixture[k] for k in ['cluster','heap','start','cut','child'])
suffix = fixture['suffix']
payload = bytearray(child + len(preview) + cluster)
payload[start:start+cut] = primary[:cut]
payload[start+cut:start+cut+20] = b'\xff\xd8\xff\xe1'+bytes(16)
payload[suffix:suffix+len(primary)-cut] = primary[cut:]
payload[child:child+len(preview)] = preview
payload.extend(bytes((-len(payload) + heap) % cluster))
count = (len(payload)-heap)//cluster
payload[3:11] = b'EXFAT   '; payload[108:111] = bytes([9,3,1])
struct.pack_into('<IIIII',payload,80,1,9,10,count,2)
payload[510:512] = b'\x55\xaa'
fat = [0]*(count+2); fat[2]=0xffffffff
first = 2+(start-heap)//cluster
for c in range(first, first+cut//cluster-1): fat[c]=c+1
terminal = 2+(child+len(preview)-1-heap)//cluster
fat[terminal]=0xffffffff
struct.pack_into('<' + str(len(fat))+'I',payload,512,*fat)
name='IMG_1234.JPG'; logical=fixture['logical']; expected=primary+bytes(logical-len(primary))+preview
entry=bytearray(96);entry[0]=0x85;entry[1]=2;entry[4]=32;entry[32]=0xc0;entry[33]=1;entry[35]=len(name)
struct.pack_into('<Q',entry,40,len(expected));struct.pack_into('<I',entry,52,first);struct.pack_into('<Q',entry,56,len(expected))
entry[64]=0xc1;entry[66:66+len(name)*2]=name.encode('utf-16-le')
checksum=0
for i,value in enumerate(entry):
 if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+value)&65535
struct.pack_into('<H',entry,2,checksum);payload[heap:heap+96]=entry
with tempfile.TemporaryDirectory() as temporary:
 base=Path(temporary); source=base/'card';source.mkdir();photo=source/name;photo.write_bytes(primary[:cut])
 image=base/'fixture.img';image.write_bytes(payload);image.chmod(0o444)
 output=base/'results'
 scan={'images':[{'path':str(photo),'status':'decode_error','bytes':cut,'mtime_ns':photo.stat().st_mtime_ns}]}
 fd=os.open(image,os.O_RDONLY);before=hashlib.sha256(image.read_bytes()).hexdigest();reads=[];original_pread=os.pread
 def aligned_read(fd,size,offset):
  assert offset%512==0 and size%512==0,(offset,size)
  reads.append(size);return original_pread(fd,size,offset)
 def read(offset,size):return imaging.read_card_range(fd,offset,size,len(payload),512)
 try:
  with patch.object(os,'pread',side_effect=aligned_read):
   assert allocation.recover(read,len(payload),source,scan,output,lambda:None)==0
  report=json.loads((output/'pipeline-report.json').read_text());row=report['photos'][0]
  assert row['quality']=='full_resolution_reconstructed',row
  rescued=Path(row['output']);assert rescued.suffix=='.JPG' and rescued.read_bytes()==expected
  assert row['output_format']=='JPEG' and row['byte_exact_source_fragments']
  assert sum(e['bytes'] for e in row['source_extents'])==len(expected)
  with Image.open(rescued) as saved:
   assert saved.getexif()[271]=='Canon' and saved.getexif()[274]==8
   saved.load();assert saved.size==(2400,1600)
   saved.seek(1);saved.load();assert saved.size==(1620,1080)
  assert sum(reads)<len(payload)*10 and not list(output.rglob('*.img'))
  assert not list(output.glob('.normal-jpeg-*'))
  assert hashlib.sha256(image.read_bytes()).hexdigest()==before
  with patch.object(normal,'MAX_SECONDS',0):
   assert normal.recover(read,len(payload),start,cluster,heap,[terminal],output,lambda:None)[1]=='normal_fragment_search_budget'
  def cancelled():raise KeyboardInterrupt()
  try:normal.recover(read,len(payload),start,cluster,heap,[terminal],output,cancelled);raise AssertionError('Cancellation swallowed')
  except KeyboardInterrupt:pass
  with patch.object(normal,'MAX_BYTES',1):
   assert normal.recover(read,len(payload),start,cluster,heap,[terminal],output,lambda:None)[1]=='normal_fragment_search_budget'
  try:normal.recover(lambda p,n:b'',len(payload),start,cluster,heap,[terminal],output,lambda:None);raise AssertionError('Short read swallowed')
  except OSError:pass
 finally:os.close(fd)
print('Normal JPEG: aligned read-only card access, complete original JPEG/EXIF/preview, bounded search and cancellation passed.')
