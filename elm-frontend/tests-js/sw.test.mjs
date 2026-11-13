import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const src = fs.readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');

function load() {
  const listeners = {};
  const opened = [];
  const sandbox = {
    self: {
      addEventListener: (type, fn) => {
        listeners[type] = fn;
      },
      registration: { showNotification: () => Promise.resolve() }
    },
    clients: {
      matchAll: () => Promise.resolve([]),
      openWindow: (url) => {
        opened.push(url);
        return Promise.resolve();
      }
    },
    console
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return { build: sandbox.buildNotification ?? vm.runInContext('buildNotification', sandbox), listeners, opened };
}

const U = 'https://atwoodknives.blogspot.com/p';
const IMG = 'https://img/x.jpg';

test('image notification', () => {
  const { build } = load();
  const { title, options } = build({ title: 'New Atwood release', body: 'B', url: U, image_url: IMG });
  assert.equal(title, 'New Atwood release');
  assert.equal(options.image, IMG);
  assert.equal(options.icon, IMG);
  assert.equal(options.badge, '/icon.png');
  assert.deepEqual({ ...options.actions[0] }, { action: 'open', title: 'Open release' });
  assert.equal(options.data.url, U);
  assert.equal(options.tag, U);
});

test('no or unsafe image falls back to site icon', () => {
  const { build } = load();
  for (const d of [{ title: 't', body: 'b', url: U }, { image_url: 'javascript:x' }, { image_url: 'http://a/b.jpg' }]) {
    const { options } = build(d);
    assert.equal(options.icon, '/icon.png');
    assert.ok(!('image' in options));
  }
});

test('empty payload', () => {
  const { build } = load();
  const { title, options } = build({});
  assert.equal(title, 'New Atwood release');
  assert.equal(options.body, '');
  assert.equal(options.data.url, '/');
  assert.ok(!('tag' in options));
  assert.ok(!('requireInteraction' in options));
});

test('sw.js does not reference icon.jpeg', () => {
  assert.ok(!src.includes('icon.jpeg'));
});

test('notificationclick opens url for action and body click', async () => {
  for (const action of ['open', '']) {
    const { listeners, opened } = load();
    let closed = false;
    let pending;
    listeners.notificationclick({
      action,
      notification: { close: () => { closed = true; }, data: { url: U } },
      waitUntil: (p) => { pending = p; }
    });
    await pending;
    assert.ok(closed);
    assert.deepEqual(opened, [U]);
  }
});

test('push with invalid JSON still shows a notification', () => {
  const shown = [];
  const { listeners } = load();
  const sandbox = {
    self: {
      addEventListener: (t, f) => { sandbox.l[t] = f; },
      registration: { showNotification: (t, o) => { shown.push([t, o]); } }
    },
    l: {},
    console: { error() {}, log() {} }
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  sandbox.l.push({ data: { json: () => { throw new Error('bad'); } }, waitUntil: () => {} });
  assert.equal(shown[0][0], 'New Atwood release');
  assert.ok(listeners.push);
});
