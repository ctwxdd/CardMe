import { createHash } from 'node:crypto';
import type { HttpHandler, HttpRequest, HttpResponseInit } from '@azure/functions';
import { parseCardMeUsage, type CardMeUsageStore } from './usage.ts';
import { readJson } from './body.ts';
import { DASHBOARD_HTML } from './dashboard.ts';

export class HttpError extends Error {
  code: string; httpStatus: number;
  constructor(code: string, httpStatus = 400) { super(code); this.code=code; this.httpStatus=httpStatus; }
}
const json = (status: number, jsonBody: unknown, headers = {}): HttpResponseInit => ({status, jsonBody, headers: {'cache-control':'no-store', 'x-content-type-options':'nosniff', ...headers}});
const websiteEvents = ['page_view','download_click','web_coffee_click'];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function authorizeAdmin(request: HttpRequest, allowed: readonly string[]) {
  const encoded = request.headers.get('x-ms-client-principal') ?? '';
  if (!encoded || encoded.length > 16384 || !/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) throw new HttpError('admin_auth_required',401);
  let p;
  try {
    const bytes = Buffer.from(encoded,'base64');
    if (bytes.toString('base64') !== encoded) throw Error();
    p = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  } catch { throw new HttpError('admin_auth_required',401); }
  if (p?.auth_typ !== 'aad' || !Array.isArray(p.claims) || !p.claims.length || p.claims.length > 128 ||
      p.claims.some((c: {typ?:unknown;val?:unknown}) => typeof c?.typ !== 'string' || typeof c.val !== 'string' || !c.typ.length || c.typ.length > 256 || !c.val.length || c.val.length > 1024)) throw new HttpError('admin_auth_required',401);
  const ids = new Set<string>(p.claims.filter((c: {typ:string}) => ['oid','http://schemas.microsoft.com/identity/claims/objectidentifier'].includes(c.typ.toLowerCase())).map((c: {val:string}) => c.val.toLowerCase()));
  if (ids.size !== 1 || !uuid.test([...ids][0])) throw new HttpError('admin_auth_required',401);
  if (!allowed.includes([...ids][0])) throw new HttpError('admin_forbidden',403);
}
export function createHandlers(options: {store: Pick<CardMeUsageStore,'save'|'summary'>; adminObjectIds: readonly string[]; websiteOrigin: string; now?:()=>number}) {
  const clock=options.now ?? Date.now;
  const buckets = new Map<string,{start:number; count:number}>();
  function charge(key:string, seconds:number, max:number) {
    const now = Math.floor(clock()/1000);
    if(buckets.size>=10000) {
      for(const [k,v] of buckets) if(now>=v.start+(k==='global'?86400:60)) buckets.delete(k);
      if(buckets.size>=10000 && !buckets.has(key)) throw new HttpError('rate_limited',429);
    }
    let b=buckets.get(key);
    if(!b || now>=b.start+seconds) {b={start:now,count:0};buckets.set(key,b);}
    if(b.count>=max) throw new HttpError('rate_limited',429);
    b.count++;
  }
  // shortcut: quotas are per Function instance; move to distributed quotas if public traffic grows.
  const source=(r:HttpRequest)=> (r.headers.get('x-azure-clientip')?.trim() || 'unknown').slice(0,128);
  const wrap=(fn:HttpHandler):HttpHandler=>async (request,context)=>{
    try { return await fn(request,context); }
    catch(e) { return json(e instanceof HttpError?e.httpStatus:503,{error:e instanceof HttpError?e.code:'temporarily_unavailable'}, e instanceof HttpError && e.httpStatus===429?{'retry-after':'60'}:{}); }
  };
  const usage=wrap(async request=>{
    if(request.method!=='POST') throw new HttpError('method_not_allowed',405);
    const type=request.headers.get('content-type')?.split(';',1)[0].trim().toLowerCase();
    if(!['application/json','text/plain'].includes(type??'')) throw new HttpError('unsupported_content_type',415);
    const length=request.headers.get('content-length');
    if(length!==null && !/^\d+$/.test(length)) throw new HttpError('invalid_content_length');
    if(length!==null && (!Number.isSafeInteger(Number(length)) || Number(length)>1024)) throw new HttpError('body_too_large',413);
    charge('source:'+source(request),60,30);
    const row=parseCardMeUsage(await readJson(request,1024));
    if(!row) throw new HttpError('invalid_schema');
    const website=websiteEvents.includes(row.event);
    if(type==='text/plain' && !website) throw new HttpError('unsupported_content_type',415);
    if(website && request.headers.get('origin')!==options.websiteOrigin) throw new HttpError('invalid_origin',403);
    charge('global',86400,10000);
    await options.store.save(row,new Date(clock()));
    return json(202,{accepted:true},website?{'access-control-allow-origin':options.websiteOrigin,'vary':'Origin'}:{});
  });
  function admin(request:HttpRequest) {
    if(request.method!=='GET') throw new HttpError('method_not_allowed',405);
    if(request.headers.get('content-length') && request.headers.get('content-length')!=='0') throw new HttpError('invalid_content_length');
    authorizeAdmin(request,options.adminObjectIds);
    charge('admin:'+source(request),60,60);
  }
  const adminData=wrap(async request=>{
    admin(request);
    const days=Number(request.query.get('days') ?? '30');
    if(![7,30,90].includes(days)) throw new HttpError('invalid_window');
    const version=request.query.get('version') ?? undefined;
    if(version && !/^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$/.test(version)) throw new HttpError('invalid_version');
    const to=new Date(clock()),from=new Date(to.getTime()-days*86400000);
    return json(200,{cardMe:await options.store.summary(from.toISOString(),to.toISOString(),version)});
  });
  const hashes=(tag:string)=>[...DASHBOARD_HTML.matchAll(new RegExp('<'+tag+'[^>]*>([\\s\\S]*?)</'+tag+'>','g'))].map(m=>"'sha256-"+createHash('sha256').update(m[1]).digest('base64')+"'").join(' ');
  const adminUI=wrap(async request=>{
    admin(request);
    return {status:200,body:DASHBOARD_HTML,headers:{'content-type':'text/html; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer',
      'content-security-policy':`default-src 'none'; script-src ${hashes('script')}; style-src ${hashes('style')}; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`}};
  });
  return {usage,adminData,adminUI};
}
