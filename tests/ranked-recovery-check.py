"""Native global ranking, byte-exact multi-run output, replay and read-only cancellation."""
import hashlib,importlib,io,os,runpy,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
from PIL import Image
root=Path(__file__).resolve().parents[1]
f=runpy.run_path(str(root/'tests/fragment-carving-check.py'))
g=importlib.import_module('preview-ranked');native=g.native
native.ROOT=Path(os.environ.get('CARDME_NATIVE_ENGINE',root/'engine'))
primary,preview=f['primary'],f['preview'];cluster,heap,start=f['cluster'],f['heap'],f['start']
cuts=[0,cluster*8,cluster*30,cluster*45,len(primary)]
positions=[start,heap+cluster*90,heap+cluster*160,heap+cluster*220]
child=positions[-1]+f['logical']-cuts[-2];payload=bytearray(child+len(preview)+cluster);expected=[]
for a,b,at in zip(cuts,cuts[1:],positions):
 payload[at:at+b-a]=primary[a:b];expected.append({'offset':at,'bytes':b-a})
 if b<len(primary):payload[at+b-a:at+b-a+16]=b'\xff\xd8'+bytes(14)
payload[child:child+len(preview)]=preview
with tempfile.TemporaryDirectory() as directory:
 folder=Path(directory);source=folder/'card.img';source.write_bytes(payload);source.chmod(0o444);output=folder/'preview.JPG';output.write_bytes(preview);fd=os.open(source,os.O_RDONLY)
 try:
  c=f['fragments'].header(fd,start,len(payload));c['_failure_prefixes']=[(start,cuts[1]+cluster+2)];c['_active_band_end']=len(payload)
  row={'offset':child,'bytes':len(preview),'output':str(output)}
  for color in (False,True):
   c['_color_ranking']=color
   result,reason=g.replay(fd,len(payload),c,[row],cluster,heap,lambda:None)
   assert result and result['data']==primary and result['source_extents']==expected,reason
   assert result['manual_review'] and result['prefix_rollback_clusters']==1
  # Ownership must be tested after rollback, not against the rejected overshot prefix.
  occupied={'offset':start+cluster*8,'quality':'full_resolution_reconstructed','sha256':hashlib.sha256(bytes(16)).hexdigest(),'source_extents':[{'offset':start+cluster*8+16,'bytes':16}]}
  c['_known_photos']=[occupied]
  result,reason=g.reconstruct(fd,len(payload),c,[row],cluster,heap,lambda:None)
  assert result and result['data']==primary,reason
  c['_known_photos']=[]
  def cancel():raise InterruptedError('cancelled')
  try:g.reconstruct(fd,len(payload),c,[row],cluster,heap,cancel);raise AssertionError('Cancel swallowed')
  except InterruptedError:pass
  with patch.object(g,'MAX_SECONDS',0):assert g.reconstruct(fd,len(payload),c,[row],cluster,heap,lambda:None)[1]=='preview_guided_time_budget'
  with patch.object(g.os,'pread',return_value=b''):
   try:g.reconstruct(fd,len(payload),c,[row],cluster,heap,lambda:None);raise AssertionError('Shortread swallowed')
   except OSError:pass
  # Deep/saved-image publication reaches native fallback and resumes without rewriting output.
  fragments=f['fragments'];allocation=importlib.import_module('fragment-rescue');saved=folder/'native-saved';saved.mkdir()
  state={'photos':[dict(row)],'fragment_candidates':[start],'fragment_failure_prefixes':{str(start):{'offset':cuts[1]+2,'algorithm_version':fragments.ALGORITHM_VERSION}}}
  with patch.object(allocation,'volume',return_value=(0,None,512,cluster,heap,len(payload)//cluster,2,b'')), patch.object(fragments,'reconstruct',return_value=(None,'no_valid_two_extent_join')), patch.object(g.legacy,'reconstruct',return_value=(None,'no_preview_guided_continuation')):
   fragments.recover(fd,len(payload),state,saved,lambda:None,lambda:None)
  published=state['photos'][-1];assert published['quality']=='manual_review' and published['review_required'];assert Path(published['output']).read_bytes()==primary
  with patch.object(allocation,'volume',return_value=(0,None,512,cluster,heap,len(payload)//cluster,2,b'')), patch.object(g,'reconstruct',side_effect=AssertionError('Reprocessed saved output')):
   fragments.recover(fd,len(payload),state,saved,lambda:None,lambda:None)
  # Native cancellation closes and reaps a running subprocess.
  guide=Image.open(output);raw=os.pread(fd,cuts[1],start);d=g.PreviewDecoder(raw);width,height,components=g.geometry(raw)[0];q=g.geometry(raw)[1];import math
  comp,h,v,qt=components[0];d.limits={c:math.ceil(1024/q[t])+1 for c,_,_,t in components};d.y_component=comp;d.y_h=h;d.y_v=v;d.y_first=next(i for i,b in enumerate(d.blocks) if b[0]==comp);d.y_quantization=q[qt];d.mcu_columns=math.ceil(width/(max(x[1] for x in components)*8));d.grid=guide.convert('YCbCr').getchannel('Y').resize((math.ceil(width/8),math.ceil(height/8)),Image.Resampling.BOX);d.error_sum=d.error_count=0;d.feed(raw[d.header_end:]);guide.close()
  calls=[0]
  def running_cancel():
   calls[0]+=1
   if calls[0]==2:raise InterruptedError('native cancelled')
  try:native.scan(d,fd,heap,len(payload),cluster,min(cluster,16384),512,10,verify=running_cancel);raise AssertionError('Native cancellation swallowed')
  except InterruptedError:pass
  assert calls[0]==2
 finally:os.close(fd)
 assert source.read_bytes()==payload
# Wrong first accepted path fails final validation, then lazy traversal tries second.
c={};calls=[]
def trial(*args,**kwargs):
 candidate=args[2];path=candidate['_replay_path'];selected=path[0] if path else 0;calls.append(path);candidate['_branch_trace'].append({'selected':selected,'options':2,'logical_offset':4096})
 return ({'data':primary},'reconstructed_review_candidate') if selected==1 else (None,'preview_guided_full_mismatch')
with patch.object(g,'_reconstruct',side_effect=trial):
 result,reason=g.replay(-1,0,c,[],1,0,lambda:None);assert result['data']==primary and calls==[(),(1,)]
print('Native ranking, both luminance/color modes, exact4fragment bytes, rollback ownership, lazy replay, cancellation and source safety passed.')
