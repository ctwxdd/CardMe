import { strict as assert } from 'node:assert';
import { test } from 'node:test';
import { createReleaseDownloads } from '../src/releases.ts';
import { createHandlers } from '../src/functions.ts';
import { DASHBOARD_HTML } from '../src/dashboard.ts';
import azureFunctions from '@azure/functions';
import type { InvocationContext } from '@azure/functions';
const { HttpRequest } = azureFunctions;
const release = (version: string, downloads: unknown) => ({ tag_name: 'v'+version, draft: false, prerelease: true,
  assets: [{ name: `CardMe-${version}.dmg`, download_count: downloads }, { name: 'source.tar.gz', download_count: 99 }] });

test('DMG-only lifetime counts include prereleases and historical downloads; cache shares concurrent refreshes', async () => {
  let calls = 0, time = 0;
  const fetcher: typeof fetch = async (url, options) => {
    calls++;
    assert.equal(options?.redirect, 'error'); assert.ok(options?.signal);
    assert(!('Authorization' in (options?.headers ?? {})));
    const legacy = String(url).includes('CardMe-releases/');
    return new Response(JSON.stringify(legacy ? [release('0.3.36', 5), release('0.3.23', 2)] :
      [release('0.3.37', 3), release('0.3.23', 4), { ...release('0.3.99', 50), draft: true }, { ...release('0.3.38', 50), assets: [] }]));
  };
  const get = createReleaseDownloads(fetcher, () => time);
  const [a, b] = await Promise.all([get(), get()]);
  assert.equal(calls, 2); assert.deepEqual(a, b); assert.equal(a.totalDmgDownloads, 14);
  assert.deepEqual(a.releases.map(r => r.version), ['0.3.37', '0.3.36', '0.3.23', '0.3.23']);
  await get(); assert.equal(calls, 2);
  time = 300001; await get(); assert.equal(calls, 4);
});

test('GitHub rate limits and malformed counts are unavailable, never falsely zero; failure cache retries', async () => {
  let time = 0, calls = 0;
  const get = createReleaseDownloads(async () => { calls++; return new Response('', { status: 403 }); }, () => time);
  assert.deepEqual((await get()).releases, []); assert.equal((await get()).totalDmgDownloads, null);
  await get(); assert.equal(calls, 2);
  time = 60001; await get(); assert.equal(calls, 4);
  for (const count of [-1, 1.5, '3', Number.MAX_SAFE_INTEGER+1]) {
    const invalid = createReleaseDownloads(async () => new Response(JSON.stringify([release('0.3.37', count)])));
    assert.equal((await invalid()).available, false);
  }
});

test('release downloads require administrator authentication before accessing GitHub; existing stats stay independent', async () => {
  const admin = '11111111-1111-4111-8111-111111111111';
  let reads = 0;
  const h = createHandlers({ store: { async save() {}, async summary() { return { appOpens: 2 }; } } as never,
    adminObjectIds: [admin], websiteOrigin: 'https://example.test', releases: async () => {
      reads++; return { available: true, checkedAt: '2026-10-12T00:00:00Z', totalDmgDownloads: 3, releases: [] };
    } });
  const req = new HttpRequest({ url: 'https://test/api/v1/admin/usage/releases', method: 'GET' });
  const ctx = {} as InvocationContext;
  assert.equal((await h.adminReleases(req, ctx)).status, 401); assert.equal(reads, 0);
  const principal = (id: string) => Buffer.from(JSON.stringify({ auth_typ: 'aad', claims: [{ typ: 'oid', val: id }] })).toString('base64');
  req.headers.set('x-ms-client-principal', principal('22222222-2222-4222-8222-222222222222'));
  assert.equal((await h.adminReleases(req, ctx)).status, 403); assert.equal(reads, 0);
  req.headers.set('x-ms-client-principal', principal(admin));
  assert.equal((await h.adminReleases(req, ctx)).status, 200); assert.equal(reads, 1);
  assert.equal((await h.adminData(req, ctx)).status, 200); assert.equal(reads, 1);
  assert.ok(DASHBOARD_HTML.includes('Website download clicks') && DASHBOARD_HTML.includes('GitHub Release downloads'));
  assert.ok(DASHBOARD_HTML.includes('loadReleases();') && DASHBOARD_HTML.includes('load();'));
  assert.ok(DASHBOARD_HTML.includes('five minutes') && DASHBOARD_HTML.includes('not unique users'));
});
