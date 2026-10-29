const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../src/shared.js'), 'utf8');

async function load(initial) {
  const data = structuredClone(initial);
  const writes = [];
  const context = vm.createContext({ chrome: { storage: { sync: {
    get: async () => structuredClone(data),
    set: async (patch) => {
      Object.assign(data, patch);
      writes.push(patch);
    },
  } } } });
  const settings = await vm.runInContext(`${source}\ngetTTSSettings()`, context);
  return {settings, data, writes};
}

test('migrates old Kokoro voice and preserves user preferences', async () => {
  const {settings, data, writes} = await load({ttsEngine:'kokoro_bf_emma',
    serverUrl:'http://my-server:18001', ttsAutoScroll:false, ttsLookAhead:30, ttsSpeed:1.5});
  assert.equal(settings.ttsEngine, 'kokoro');
  assert.equal(settings.ttsVoice, 'bf_emma');
  assert.equal(data.ttsVoices.kokoro, 'bf_emma');
  assert.equal(data.ttsAutoScroll, false);
  assert.equal(data.ttsLookAhead, 30);
  assert.equal(data.ttsSpeed, 1.5);
  assert.equal(data.serverUrl, 'http://my-server:18001');
  assert.equal(writes.length, 1);
});

test('new settings retain Google fallback and Pocket has a local default', async () => {
  assert.equal((await load({})).settings.ttsEngine, 'google-translate');
  assert.equal((await load({ttsEngine:'pocket'})).settings.ttsVoice, 'alba');
});

test('per-engine voice wins and canonical selections need no migration', async () => {
  const {settings, writes} = await load({ttsEngine:'pocket', ttsVoice:'af_heart',
    ttsVoices:{kokoro:'af_heart', pocket:'anna'}});
  assert.equal(settings.ttsVoice, 'anna');
  assert.equal(writes.length, 0);
});

test('retired Pocket selections fall back to Alba without changing Kokoro', async () => {
  for (const voice of ['marius', 'javert']) {
    const active = await load({ttsEngine:'pocket', ttsVoice:voice});
    assert.equal(active.settings.ttsVoice, 'alba');
    assert.equal(active.data.ttsVoices.pocket, 'alba');
    const other = await load({ttsEngine:'kokoro', ttsVoice:'af_heart',
      ttsVoices:{kokoro:'af_heart', pocket:voice}});
    assert.equal(other.settings.ttsVoice, 'af_heart');
    assert.equal(other.data.ttsVoices.pocket, 'alba');
  }
});
