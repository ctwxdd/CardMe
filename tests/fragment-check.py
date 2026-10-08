#!/usr/bin/env python3
"""Generate a fragmented exFAT card and recover it without a private map or image file."""
import hashlib, importlib, io, json, struct, sys, tempfile
from pathlib import Path
from PIL import Image
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'engine'))
engine = importlib.import_module('fragment-rescue')
photo = Image.new('RGB', (1024, 768))
photo.putdata([(x * 255 // 1024, y * 255 // 768, (x + y) * 255 // 1792) for y in range(768) for x in range(1024)])
t = io.BytesIO(); photo.resize((64, 48)).save(t, format='JPEG');thumb = t.getvalue()
exif = b'Exif\0\0II' + struct.pack('<HI', 42, 8) + struct.pack('<HI', 0, 14) + struct.pack('<H', 2)
exif += struct.pack('<HHII', 513, 4, 1, 44) + struct.pack('<HHII', 514, 4, 1, len(thumb)) + bytes(4) + thumb
b = io.BytesIO(); photo.save(b, format='JPEG', quality=85, exif=exif);jpeg=b.getvalue()
cs, count, heap = 4096, 1024, 5120
card = bytearray(heap + count * cs)
card[3:11] = b'EXFAT   ';card[108:111]=bytes([9,3,1])
struct.pack_into('<IIIII',card,80,1,9,10,count,2)
card[510:512] = b'\x55\xaa'
fat = [0] * (count + 2); fat[2]=0xffffffff
clusters = list(range(4,4+((len(jpeg)+cs-1)//cs)*3,3))
for i,c in enumerate(clusters):
 fat[c]=clusters[i+1] if i+1<len(clusters) else 0xffffffff
 offset=heap+(c-2)*cs;data=jpeg[i*cs:(i+1)*cs];card[offset:offset+len(data)]=data
struct.pack_into('<' + str(len(fat))+'I',card,512,*fat)
e=bytearray(96);e[0]=0x85;e[1]=2;e[4]=32;e[32]=0xc0;e[33]=1;e[35]=8
struct.pack_into('<Q',e,40,len(jpeg));struct.pack_into('<I',e,52,4);struct.pack_into('<Q',e,56,len(jpeg))
e[64]=0xc1;e[66:82]='test.jpg'.encode('utf-16-le')
checksum=0
for i,value in enumerate(e):
 if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+value)&65535
struct.pack_into('<H',e,2,checksum);card[heap:heap+96]=e
original=bytes(card);reads=[]
def read(offset,length):
 assert 0<=offset and offset+length<=len(card)
 reads.append((offset,length));return bytes(card[offset:offset+length])
with tempfile.TemporaryDirectory() as temp:
 base=Path(temp);source=base/'source';source.mkdir();p=source/'test.jpg';p.write_bytes(jpeg[:cs])
 scan={'images':[{'path':str(p),'status':'decode_error','bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}]}
 output=base/'results'
 assert engine.recover(read,len(card),source,scan,output,lambda:None)==0
 report=json.loads((output/'pipeline-report.json').read_text());assert report['quality_counts']=={'full_resolution':1},report
 target=Path(report['photos'][0]['output']);assert target.read_bytes()==jpeg
 mapped=json.loads((output/'fragment-map.json').read_text());assert len(mapped['photos'][0]['extents'])==len(clusters)
 assert engine.recover(read,len(card),source,scan,output,lambda:None)==0
 target.write_bytes(b'conflict');assert engine.recover(read,len(card),source,scan,output,lambda:None)==2
 assert target.read_bytes()==b'conflict'
 def cancelled():raise KeyboardInterrupt
 try:engine.recover(read,len(card),source,scan,base/'cancelled',cancelled);raise AssertionError('Ignored cancellation')
 except KeyboardInterrupt:pass
 assert not list((base/'cancelled').rglob('*.jpg'))
 p.write_bytes(b'changed');assert engine.recover(read,len(card),source,scan,base/'changed',lambda:None)==2
 def changed_allocation():card[512+4*4] ^= 1
 try:
  engine.recover(read,len(card),source,{'images':[{**scan['images'][0], 'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}]},base/'allocation-changed',changed_allocation)
  raise AssertionError('Changed allocation accepted')
 except engine.SourceChanged:pass
 card[:]=original
 assert not (base/'allocation-changed/pipeline-report.json').exists()
 assert bytes(card)==original and not list(base.rglob('*.img'))
 assert sum(n for _,n in reads)<len(card)*5
# A displaced FAT sector is inferred from the generated card, not supplied as a recipe.
with tempfile.TemporaryDirectory() as temp:
 base=Path(temp);source=base/'source';source.mkdir();p=source/'test.jpg';p.write_bytes(jpeg[:cs])
 moved=[c+144 for c in clusters]
 shifted_fat=[0]*(count+2);shifted_fat[2]=0xffffffff
 for i,c in enumerate(moved):
  shifted_fat[c]=moved[i+1] if i+1<len(moved) else 0xffffffff
  offset=heap+(c-2)*cs;piece=jpeg[i*cs:(i+1)*cs];card[offset:offset+len(piece)]=piece
 for c in range(200,250):shifted_fat[c]=c+1
 shifted_fat[250]=0xffffffff
 shifted_fat[256:384]=shifted_fat[128:256]
 shifted_fat[128:256]=[0xdeadbeef]*128
 struct.pack_into('<'+str(len(shifted_fat))+'I',card,512,*shifted_fat)
 struct.pack_into('<I',e,52,moved[0]);checksum=0
 for i,value in enumerate(e):
  if i not in (2,3):checksum=(((checksum&1)<<15)+(checksum>>1)+value)&65535
 struct.pack_into('<H',e,2,checksum);card[heap:heap+96]=e
 scan={'images':[{'path':str(p),'status':'decode_error','bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}]}
 output=base/'results';snapshot=bytes(card)
 assert engine.recover(read,len(card),source,scan,output,lambda:None)==0
 report=json.loads((output/'pipeline-report.json').read_text())
 assert report['quality_counts']=={'full_resolution':1}
 assert Path(report['photos'][0]['output']).read_bytes()==jpeg
 mapped=json.loads((output/'fragment-map.json').read_text());assert mapped['hypotheses']==[{'entries':128,'first':128,'last':384}]
 assert bytes(card)==snapshot
print('Automatic fragment check passed: no recipe/image dependency, exact JPEG, collision, cancellation and unchanged source.')
