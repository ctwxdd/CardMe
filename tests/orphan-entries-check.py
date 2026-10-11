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
