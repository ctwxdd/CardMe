import assert from 'node:assert/strict';
import fs from 'node:fs';
import {TableClient} from '@azure/data-tables';
import {AzureCliCredential} from '@azure/identity';
const [from,to,evidence]=process.argv.slice(2);
assert(from && to && evidence && from!==to,'Usage: node migrate-statistics.mjs SOURCE_TABLE_ENDPOINT DESTINATION_TABLE_ENDPOINT EVIDENCE_JSON');
const credentials=new AzureCliCredential();
const source=new TableClient(from,'CardMeUsage',credentials),destination=new TableClient(to,'CardMeUsage',credentials);
const clean=row=>Object.fromEntries(Object.entries(row).filter(([k])=>!['etag','timestamp'].includes(k)));
const key=row=>row.partitionKey+'/'+row.rowKey;
const old=new Map(),existing=new Map();
for await(const row of source.listEntities()) old.set(key(row),clean(row));
for await(const row of destination.listEntities()) existing.set(key(row),clean(row));
const groups=new Map();
for(const [k,row] of old){
 if(existing.has(k)){assert.deepEqual(existing.get(k),row,'Existing event differs; refusing to overwrite');continue;}
 const group=groups.get(row.partitionKey)??[];group.push(row);groups.set(row.partitionKey,group);
}
for(const group of groups.values())for(let i=0;i<group.length;i+=100)await destination.submitTransaction(group.slice(i,i+100).map(row=>['create',row]));
const verified=new Map();for await(const row of destination.listEntities())verified.set(key(row),clean(row));
for(const [k,row] of old)assert.deepEqual(verified.get(k),row,'Migration verification failed');
fs.writeFileSync(evidence,JSON.stringify({migrated:old.size,verified:true,completedAt:new Date().toISOString()},null,2));
console.log(`Verified ${old.size} migrated events. Source is unchanged.`);
