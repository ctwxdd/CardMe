import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import type { TableClient } from '@azure/data-tables';
import azureFunctions from '@azure/functions';
import type { HttpRequest as AzureRequest, InvocationContext } from '@azure/functions';
const {HttpRequest}=azureFunctions;
import { CardMeUsageStore, parseCardMeUsage } from '../src/usage.ts';
import { createHandlers } from '../src/functions.ts';
const admin='11111111-1111-4111-8111-111111111111';
const websiteOrigin='https://witty-meadow-00543f01e.6.azurestaticapps.net';
const report=(patch={})=>({schema_version:1,event_id:'12345678-1234-4234-8234-123456789abc',event:'rescue_complete',app_version:'0.3.24',mode:'normal',full_size:2,previews:1,thumbnails:0,review:0,unrecovered:3,...patch});
const webReport=(patch={})=>report({event:'page_view',app_version:'web',mode:'none',full_size:0,previews:0,unrecovered:null,...patch});
const scanReport=(patch={})=>report({schema_version:2,event:'scan_finished',mode:'normal',full_size:0,previews:0,unrecovered:null,scan_total:2222,scan_flagged:20,scan_result:'completed',...patch});
const request=(input:unknown,method='POST',contentType='application/json')=>new HttpRequest({url:'https://test/api/v1/usage',method,headers:{'content-type':contentType},...(method==='GET'?{}:{body:{string:JSON.stringify(input)}})});
const ctx={} as InvocationContext;

test("exact schema rejects private fields, invalid counts and misleading non-rescue counters", () => {
  assert.ok(parseCardMeUsage(report()));
  assert.ok(parseCardMeUsage(report({ mode: "deep", unrecovered: null })));
  for (const patch of [{ filename: "x.jpg" }, { install_id: "id" }, { path: "/Volumes/card" }, { exif: {} }, { full_size: -1 }, { full_size: 1.5 }, { full_size: 1000001 }, { event: "other" }, { event: ["rescue_complete"] }, { mode: ["normal"] }, { mode: "deep" }, { mode: "none" }, { event: "coffee_click" }, { app_version: "x".repeat(33) }]) assert.equal(parseCardMeUsage(report(patch)), null);
});
test("deduplication, aggregate counts and cleanup preserve unknown Deep missing counts", async () => {
  const rows = new Map<string, Record<string, unknown>>();
  let filter = "";
  const client = {
    async createEntity(row: Record<string, unknown>) { if(rows.has(String(row.rowKey))) throw { statusCode: 409 }; rows.set(String(row.rowKey),row); },
    async *listEntities(options: { queryOptions: { filter: string } }) { filter = options.queryOptions.filter; for (const row of rows.values()) if(filter.includes(`PartitionKey eq '${row.partitionKey}'`)) yield row; },
    async deleteEntity(_: string, key: string) { rows.delete(key); },
  } as unknown as TableClient;
  const store = new CardMeUsageStore(client), now = new Date("2026-10-08T12:00:00Z");
  await store.save(parseCardMeUsage(report())!, now);
  await store.save(parseCardMeUsage(report())!, now);
  await store.save(parseCardMeUsage(report({ event_id: "22345678-1234-4234-8234-123456789abc", mode: "deep", unrecovered: null }))!,now);
  assert.equal(rows.size,2);
  const totals = await store.summary("2026-10-01", "2026-10-09");
  assert.equal(totals.rescues,2); assert.equal(totals.fullSize,4); assert.equal(totals.unrecovered,3); assert.equal(totals.unknownUnrecovered,1);
  assert.equal((await store.summary("2026-10-01", "2026-10-09", "0.1.0")).rescues,0);
  assert.equal(await store.prune(now, 1),1); assert.ok(filter.includes("receivedAt lt"));
});
test("website counts stay independent of app-version filters and daily counts reconcile", async () => {
  const rows: Record<string, unknown>[] = [];
  const client = { async createEntity(row: Record<string, unknown>) { rows.push(row); }, async *listEntities(options: { queryOptions: { filter: string } }) {
    for (const row of rows) if (options.queryOptions.filter.includes(`PartitionKey eq '${row.partitionKey}'`)) yield row;
  }} as unknown as TableClient;
  const store = new CardMeUsageStore(client);
  await store.save(parseCardMeUsage(webReport())!, new Date("2026-10-08T00:00:00Z"));
  await store.save(parseCardMeUsage(webReport({ event: "download_click" }))!, new Date("2026-10-09T00:00:00Z"));
  await store.save(parseCardMeUsage(report())!, new Date("2026-10-08T00:00:00Z"));
  const totals = await store.summary("2026-10-01", "2026-10-10", "0.3.24");
  assert.equal(totals.pageViews, 1); assert.equal(totals.downloadClicks, 1); assert.equal(totals.rescues, 1);
  assert.deepEqual(totals.daily.map(d => d.day), ["2026-10-08", "2026-10-09"]);
  assert.equal(totals.daily.reduce((sum, d) => sum + d.fullSize, 0), totals.fullSize);
  const filtered = await store.summary("2026-10-01", "2026-10-10", "0.3.22");
  assert.equal(filtered.pageViews, 1); assert.equal(filtered.rescues, 0);
});
test('scan V2 counts and terminal outcomes are strict; existing V1 events remain valid', async () => {
  assert.ok(parseCardMeUsage(report()));
  for (const scan_result of ['completed','failed','cancelled']) assert.ok(parseCardMeUsage(scanReport({scan_result})));
  for (const patch of [{schema_version:1},{event:'app_open'},{schema_version:3},{scan_total:-1},{scan_total:10},{scan_flagged:1.5},{scan_result:'other'},{mode:'deep'},{full_size:1},{path:'private'}]) assert.equal(parseCardMeUsage(scanReport(patch)),null);
  const rows: Record<string, unknown>[] = [];
  const client = {async createEntity(row: Record<string, unknown>) {rows.push(row);}, async *listEntities(options: {queryOptions: {filter: string}}) {
    for (const row of rows) if(options.queryOptions.filter.includes(`PartitionKey eq '${row.partitionKey}'`)) yield row;
  }} as unknown as TableClient;
  const store = new CardMeUsageStore(client), now = new Date('2026-10-08T00:00:00Z');
  await store.save(parseCardMeUsage(report())!,now);
  assert.equal((await store.summary('2026-10-01','2026-10-09')).scanReports,0);
  for (const scan_result of ['completed','failed','cancelled']) await store.save(parseCardMeUsage(scanReport({scan_result}))!,now);
  const totals=await store.summary('2026-10-01','2026-10-09');
  assert.equal(totals.scanReports,3);assert.equal(totals.totalScanned,6666);assert.equal(totals.scanFlagged,60);
  assert.equal(totals.scansCompleted,1);assert.equal(totals.scansFailed,1);assert.equal(totals.scansCancelled,1);
  assert.equal(totals.daily[0].totalScanned,totals.totalScanned);assert.equal(totals.unrecovered,3);
  const handlers=createHandlers({store,adminObjectIds:[admin],websiteOrigin});
  assert.equal((await handlers.usage(request(scanReport()),ctx)).status,202);
});
test('independent ingestion bounds bodies, schemas, origin and source quotas',async()=>{
  let saved=0;
  const store={async save(){saved++;},async summary(){return {};}} as never;
  const h=createHandlers({store,adminObjectIds:[admin],websiteOrigin});
  assert.equal((await h.usage(request(report()),ctx)).status,202);
  assert.equal((await h.usage(request(report({path:'/private'})),ctx)).status,400);
  assert.equal((await h.usage(request(report(),'GET'),ctx)).status,405);
  assert.equal((await h.usage(request(report(),'POST','text/plain'),ctx)).status,415);
  assert.equal((await h.usage(request({value:'x'.repeat(1025)}),ctx)).status,413);
  for(const event of ['page_view','download_click','web_coffee_click']){
    const req=request(webReport({event}),'POST','text/plain;charset=UTF-8');req.headers.set('origin',websiteOrigin);
    const r=await h.usage(req,ctx);assert.equal(r.status,202);assert.equal((r.headers as Record<string,string>)['access-control-allow-origin'],websiteOrigin);
  }
  for(const origin of ['https://getpickology.com','https://bad.example','null','']){
    const req=request(webReport());req.headers.set('origin',origin);assert.equal((await h.usage(req,ctx)).status,403);
  }
  assert.equal(saved,4);
  let limited=false;for(let i=0;i<35;i++)if((await h.usage(request(report()),ctx)).status===429)limited=true;assert(limited);
  const large={method:'POST',headers:new Headers({'content-type':'application/json'}),body:new ReadableStream<Uint8Array>({start(c){c.enqueue(new Uint8Array(2048));c.close();}})} as unknown as AzureRequest;
  assert.equal((await createHandlers({store,adminObjectIds:[admin],websiteOrigin}).usage(large,ctx)).status,413);
});
test('dashboard requires a bounded platform Entra principal and explicit administrator',async()=>{
  let reads=0;
  const h=createHandlers({store:{async save(){},async summary(){reads++;return {};}} as never,adminObjectIds:[admin],websiteOrigin});
  const principal=(claims:unknown,auth_typ='aad')=>Buffer.from(JSON.stringify({auth_typ,claims})).toString('base64');
  for(const header of ['', 'invalid', principal([{typ:'oid',val:admin}],'anonymous'),principal([{typ:'oid',val:admin},{typ:'oid',val:'22222222-2222-4222-8222-222222222222'}]),principal([{typ:'oid',val:admin},{typ:'extra',val:'x'.repeat(1025)}])]){
    const req=request({},'GET');req.headers.set('x-ms-client-principal',header);assert.equal((await h.adminData(req,ctx)).status,401);
  }
  const req=request({},'GET');req.headers.set('x-ms-client-principal',principal([{typ:'oid',val:admin}]));
  assert.equal((await h.adminData(req,ctx)).status,200);assert.equal(reads,1);
  req.query.set('version',"x' or true");assert.equal((await h.adminData(req,ctx)).status,400);req.query.delete('version');
  req.query.set('days','999');assert.equal((await h.adminData(req,ctx)).status,400);req.query.delete('days');
  const ui=await h.adminUI(req,ctx);assert.equal(ui.status,200);assert(String(ui.body).includes('CardMe statistics'));assert(!String(ui.body).includes('Pickology'));
  assert(String((ui.headers as Record<string,string>)['content-security-policy']).includes("'sha256-"));
  req.headers.set('x-ms-client-principal',principal([{typ:'oid',val:'22222222-2222-4222-8222-222222222222'}]));assert.equal((await h.adminData(req,ctx)).status,403);
  assert.equal(reads,1);
});
test('service resources and public route exceptions remain independent',async()=>{
  const fs=await import('node:fs/promises');
  const infra=await fs.readFile(new URL('../infra/main.bicep',import.meta.url),'utf8');
  const index=await fs.readFile(new URL('../src/index.ts',import.meta.url),'utf8');
  assert(!infra.toLowerCase().includes('pickologycontrolplane'));
  assert(!infra.includes('KeyVault') && !infra.includes('dnsZones'));
  assert(infra.includes("param storageAccountName string = 'cardmeusage2026'"));
  assert(infra.includes('@secure()\nparam entraClientSecret string'));
  assert(infra.includes("'/api/v1/usage'") && infra.includes("'/api/health'"));
  assert(!infra.includes("'/api/v1/admin/usage'"));
  assert(index.includes("route:'v1/usage'") && !index.includes('Pickology'));
});
test('public counters expose only fixed 90-day totals and coalesce concurrent reads',async()=>{
 let reads=0,now=Date.parse('2026-10-12T00:00:00Z'),from='';
 const store={async save(){},async summary(start:string){reads++;from=start;await Promise.resolve();return {rescues:12,fullSize:2000,appOpens:99,daily:[{day:'private'}]};}} as never;
 const h=createHandlers({store,adminObjectIds:[admin],websiteOrigin,now:()=>now});
 const results=await Promise.all([h.publicTotals(request({},'GET'),ctx),h.publicTotals(request({},'GET'),ctx)]);
 assert.equal(reads,1);assert.equal(from,'2026-07-14T00:00:00.000Z');
 for(const r of results){assert.equal(r.status,200);assert.deepEqual((r as {jsonBody:unknown}).jsonBody,{windowDays:90,rescueSessions:12,fullSizePhotos:2000});}
 const invalid=request({},'GET');invalid.query.set('version','private');assert.equal((await h.publicTotals(invalid,ctx)).status,400);
 now+=300001;assert.equal((await h.publicTotals(request({},'GET'),ctx)).status,200);assert.equal(reads,2);
 assert.equal((await h.publicTotals(request({}),ctx)).status,405);
});
