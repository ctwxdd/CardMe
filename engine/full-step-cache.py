"""Research-only exact-byte cache; alternative source positions remain separate paths."""
import hashlib,importlib
coding=importlib.import_module('jpeg-checkpoint')
def step(decoder,raw,cache,check):
 check();key=hashlib.sha256(raw).digest();row=cache.get(key)
 if row is not None and row[0]==raw:
  trial=row[1]
  if trial is None:return None
  result=trial.clone();result.error_sum,result.error_count=trial.error_sum,trial.error_count
  return result
 trial=decoder.clone()
 try:trial.feed(raw,check)
 except coding.Invalid:trial=None
 if len(cache)>=8:del cache[next(iter(cache))]
 cache[key]=(raw,trial)
 return trial
