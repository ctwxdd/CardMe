import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const code=fs.readFileSync(new URL('../website/dist/totals.js',import.meta.url),'utf8');
async function run(value,{offline=false,ok=true}={}){
 const fields={},target={hidden:true,querySelector:selector=>fields[selector]??(fields[selector]={textContent:''})};
 let requests=0;
 await vm.runInNewContext(code,{Intl,Number,Object,AbortSignal,document:{documentElement:{lang:'en'},querySelector:()=>target},fetch:async(url,options)=>{
  requests++;assert.equal(url,'https://cardme-control-plane.azurewebsites.net/api/v1/public/totals');
  assert.equal(options.credentials,'omit');assert.equal(options.referrerPolicy,'no-referrer');assert(!options.body);
  if(offline)throw Error('offline');return {ok,json:async()=>value};
 }});
 return {target,fields,requests};
}
const result=await run({windowDays:90,rescueSessions:20,fullSizePhotos:1234});
assert(!result.target.hidden);assert.equal(result.fields['[data-total="fullSizePhotos"]'].textContent,'1,234');assert.equal(result.requests,1);
for(const invalid of [null,{}, {windowDays:90,rescueSessions:-1,fullSizePhotos:20},{windowDays:30,rescueSessions:2,fullSizePhotos:20},{windowDays:90,rescueSessions:2,fullSizePhotos:'<script>'},{windowDays:90,rescueSessions:2,fullSizePhotos:20,event_id:'private'}])assert((await run(invalid)).target.hidden);
assert((await run({}, {offline:true})).target.hidden);assert((await run({}, {ok:false})).target.hidden);
assert(!(await run({windowDays:90,rescueSessions:0,fullSizePhotos:0})).target.hidden);
console.log('Public totals: exact aggregate fields, safe formatting, no identity or upload, and quiet failure passed.');
