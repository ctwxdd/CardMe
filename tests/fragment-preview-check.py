#!/usr/bin/env python3
import hashlib, importlib, io, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))
engine=importlib.import_module('fragment-preview')
photo=Image.new('RGB',(1620,1080))
photo.paste('orange',(0,0,810,540))
out=io.BytesIO();photo.save(out,format='JPEG',quality=95);raw=out.getvalue()
cluster,heap=4096,5120;start=heap+5*cluster+123;cut=cluster-123;suffix=heap+64*cluster
payload=bytearray(suffix+len(raw)-cut+cluster)
payload[start:start+cut]=raw[:cut]
payload[suffix:suffix+len(raw)-cut]=raw[cut:]
candidate={'offset':heap+cluster,'preview_logical':start-(heap+cluster),'preview_bytes':len(raw),'thumbnail':photo.resize((160,107))}
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'card.img';path.write_bytes(payload);path.chmod(0o444)
 fd=os.open(path,os.O_RDONLY)
 try:
  described=engine.describe(fd,start,len(payload));assert described['dimensions']==[1620,1080]
  result,reason=engine.reconstruct(fd,len(payload),candidate,[described],cluster,heap,lambda:None)
  assert reason=='reconstructed_preview' and result['data']==raw,(reason,result)
  assert result['source_extents']==[{'offset':start,'bytes':cut},{'offset':suffix,'bytes':len(raw)-cut}]
  assert path.read_bytes()==payload
  indexed, reason = engine.reconstruct(fd,len(payload),candidate,[described],cluster,heap,lambda:None,[suffix+len(raw)-cut])
  assert reason == 'reconstructed_preview' and indexed['data'] == raw
  def cancel():raise KeyboardInterrupt
  try:engine.reconstruct(fd,len(payload),candidate,[described],cluster,heap,cancel);raise AssertionError('cancel ignored')
  except KeyboardInterrupt:pass
  with patch.object(engine,'MAX_END_CHECKS',1):
   assert engine.reconstruct(fd,len(payload),candidate,[described],cluster,heap,lambda:None)[1]=='preview_endpoint_search_budget'
  assert engine.reconstruct(fd,len(payload),candidate,[described,described],cluster,heap,lambda:None)[1]=='ambiguous_preview_joins'
  with patch.object(engine.os,'pread',return_value=b''):
   try:engine.describe(fd,start,len(payload));raise AssertionError('short read ignored')
   except OSError:pass
 finally:os.close(fd)
print('Fragmented preview checks passed: exact bytes, alignment, ambiguity, cancellation, bounded work, short reads and read-only source.')
