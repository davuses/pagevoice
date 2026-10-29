const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ext = path.resolve(__dirname, '../dist-chrome');
const serverUrl = process.env.TTS_SERVER_URL || 'http://127.0.0.1:18001';
(async () => {
  const context = await chromium.launchPersistentContext('', {
    executablePath: process.env.CHROMIUM_EXECUTABLE,
    channel: process.env.CHROMIUM_EXECUTABLE ? undefined : 'chromium',
    headless: true,
    acceptDownloads: true,
    args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`,
      '--no-sandbox', '--autoplay-policy=no-user-gesture-required'],
  });
  try {
    const worker = context.serviceWorkers()[0] || await context.waitForEvent('serviceworker');
    // Keep the PCM actually delivered over HTTP so the download check catches
    // dropped/reordered/truncated chunks, including the final speech samples.
    const wireReads = [];
    context.on('response', response => {
      if (response.url() !== `${serverUrl}/tts/stream`) return;
      wireReads.push(response.body().then(body => Buffer.concat(
        body.toString('utf8').trim().split('\n').map(line => JSON.parse(line))
          .filter(message => message.pcm_b64)
          .map(message => Buffer.from(message.pcm_b64, 'base64'))
      )));
    });
    const id = worker.url().split('/')[2];
    console.log('Extension loaded', id);
    await worker.evaluate(async (serverUrl) => {
      await chrome.storage.sync.set({ttsEngine:'kokoro_af_heart', serverUrl, ttsLookAhead:30, ttsAutoScroll:true});
    }, serverUrl);
    const popup = await context.newPage();
    await popup.goto(`chrome-extension://${id}/popup.html`);
    await popup.waitForFunction(() => document.querySelector('#voice-select').value === 'af_heart');
    assert.equal(await popup.locator('#tts-select').inputValue(), 'kokoro');
    console.log('Legacy voice migration PASS');
    const page = await context.newPage();
    page.setDefaultTimeout(120000);
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.route('http://127.0.0.1:18003/**', route => route.fulfill({
      contentType:'text/html', body:'<!doctype html><html><head><title>Read test</title></head><body><div style="height:1500px">Spacer</div><article><p id="read" style="font-size:24px">Nobody in math is ever going to forget the year 2026. Unless this is really the end of the subject.</p></article><div style="height:1500px"></div></body></html>',
    }));
    await page.goto('http://127.0.0.1:18003/article');
    await page.waitForTimeout(500);
    for (const engine of ['pocket','kokoro']) {
      const firstWireRead = wireReads.length;
      await popup.bringToFront();
      await popup.locator('#tts-select').selectOption(engine);
      await popup.waitForFunction(() => !document.querySelector('#voice-select').disabled);
      assert.equal(await popup.locator('#speed-row').isVisible(), engine === 'kokoro');
      if (engine === 'kokoro') {
        await worker.evaluate(() => chrome.storage.sync.set({ttsAutoScroll:false}));
      }
      await page.bringToFront();
      await page.evaluate(() => {
        window.scrollTo(0,0);
        const range = document.createRange();
        range.selectNodeContents(document.querySelector('#read'));
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
      });
      await page.waitForTimeout(200);
      await worker.evaluate(async () => {
        const tabs = await chrome.tabs.query({active:true, currentWindow:true});
        await chrome.tabs.sendMessage(tabs[0].id, {action:'readSelection'});
      });
      await page.waitForSelector('.tts-player-host');
      await page.waitForFunction(() => Array.from(CSS.highlights.values()).some(h => h.size > 0), null, {timeout:120000});
      if (engine === 'kokoro') {
        assert.equal(await page.evaluate(() => window.scrollY),0);
        await page.locator('button[title="Jump to current sentence"]').click();
        const stored = await worker.evaluate(() => chrome.storage.sync.get('ttsAutoScroll'));
        assert.equal(stored.ttsAutoScroll,false);
        console.log('Jump to sentence with auto-scroll disabled PASS');
      }
      await page.waitForFunction(() => window.scrollY > 300);
      console.log(engine, 'playback/highlight/auto-scroll PASS');
      if (engine === 'pocket') {
        await page.waitForTimeout(600);
        await page.mouse.wheel(0, -500);
        await page.waitForTimeout(200);
        const manualY = await page.evaluate(() => window.scrollY);
        await page.waitForTimeout(900);
        assert(Math.abs(await page.evaluate(() => window.scrollY) - manualY) < 2);
        console.log('Manual scrolling suspends following PASS');
        await page.locator('button[title="Jump to current sentence"]').click();
        await page.waitForFunction(y => window.scrollY > y + 100, manualY);
        console.log('Jump after manually scrolling away PASS');
      }
      await page.waitForFunction(() => !document.querySelector('.tts-player-host').shadowRoot.querySelector('.time-display').textContent.includes('…'));
      const next = page.locator('.tts-player-host button[title="Next sentence"]');
      await next.click();
      await page.waitForTimeout(200);
      const previous = page.locator('.tts-player-host button[title="Previous sentence"]');
      await previous.click();
      const downloadEvent = page.waitForEvent('download');
      await page.locator('.tts-player-host button[title="Download audio"]').click();
      const download = await downloadEvent;
      const downloaded = fs.readFileSync(await download.path());
      assert.equal(downloaded.toString('ascii',0,4),'RIFF');
      assert(downloaded.length > 44);
      const wirePcm = Buffer.concat(await Promise.all(wireReads.slice(firstWireRead)));
      assert(wirePcm.length > 0, 'must capture the HTTP audio');
      assert.deepEqual(downloaded.subarray(44), wirePcm,
        'WAV must preserve every streamed sample in order');
      if (process.env.PCM_CAPTURE_DIR) {
        const raw = fs.readFileSync(path.join(process.env.PCM_CAPTURE_DIR, `${engine}.wav`));
        assert.deepEqual(downloaded.subarray(44), raw.subarray(44),
          'WAV must match raw model output after Int16 conversion');
      }
      console.log(engine, 'HTTP PCM -> downloaded WAV byte equality PASS');
      await page.locator('.tts-player-host .close-button').click();
      assert.equal(await page.locator('.tts-player-host').count(),0);
      console.log(engine,'sentence navigation/WAV/cleanup PASS');
    }
    assert.deepEqual(pageErrors, []);
    console.log('BROWSER SMOKE PASS');
  } finally { await context.close(); }
})().catch(e => { console.error(e); process.exitCode=1; });
