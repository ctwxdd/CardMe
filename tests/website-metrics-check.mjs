import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const code = fs.readFileSync(new URL('../website/dist/metrics.js', import.meta.url), 'utf8');
function run(navigator = {}, broken = false) {
  const events = []; let click;
  vm.runInNewContext(code, {navigator, crypto: {randomUUID: () => 'random-event-id'},
    document: {addEventListener: (_, fn) => {click = fn;}}, fetch: (_, options) => {
      events.push({body: JSON.parse(options.body), options});
      if (broken) throw Error('offline');
      return Promise.reject(Error('offline'));
    }});
  return {events, click};
}
const result = run();
assert.equal(result.events[0].body.event, 'page_view');
for (const [href, event] of [['https://github.com/ctwxdd/CardMe-releases/releases/download/v0.3.23/CardMe-0.3.23.dmg','download_click'],['https://ko-fi.com/alittleseal','web_coffee_click']]) {
  result.click({target: {closest: () => ({getAttribute: () => href, hasAttribute: () => href === 'https://github.com/ctwxdd/CardMe-releases/releases/download/v0.3.23/CardMe-0.3.23.dmg'})}});
  assert.equal(result.events.at(-1).body.event, event);
}
result.click({target: {}});
assert.equal(result.events.length, 3);
for (const {body, options} of result.events) {
  assert.deepEqual(Object.keys(body).sort(), ['schema_version','event_id','event','app_version','mode','full_size','previews','thumbnails','review','unrecovered'].sort());
  assert.equal(options.credentials, 'omit'); assert.equal(options.referrerPolicy, 'no-referrer');
}
assert.equal(run({doNotTrack:'1'}).events.length, 0);
assert.equal(run({globalPrivacyControl:true}).events.length, 0);
const offline = run({}, true); assert.doesNotThrow(() => offline.click({target:{closest:()=>({getAttribute:()=>'https://github.com/ctwxdd/CardMe-releases/releases/download/v0.3.23/CardMe-0.3.23.dmg', hasAttribute:()=>true})}}));
console.log('Website metrics: anonymous schema, privacy signals, click reporting and offline navigation passed.');
