# PageVoice — browser extension

A cross-browser (Chrome/MV3 and Firefox/MV2) extension that reads web text aloud.
It has three engines:

- **Kokoro** — high-quality neural TTS, streamed from your own local
  [kokoro-server](../server). Low latency on long text and a karaoke-style
  highlight that follows along as it reads.
- **Google Translate** — a zero-setup fallback that fetches audio directly from
  Google's public translate TTS endpoint (no local server needed).
- **Pocket TTS** — 12 preset voices, streamed from the
  same local server. Runs on CPU with sentence highlighting and auto-scroll.

> **Kokoro and Pocket require the companion server.** Install and run
> [kokoro-server](../server) first; by default the extension talks to it at
> `http://localhost:18001` (configurable in the popup). Google Translate works
> without it.

## Features

- **Read the main article** — best-effort detection of the page's main content
  (popup button or context menu).
- **Read an element** — hover/click a paragraph or section to read just that
  (popup button or context menu).
- **Read from here to the end** — read from the right-clicked spot onward.
- Streaming player with play/pause, seek, and a WAV download (both local engines).
- Sentence-level highlight synced to the audio, with optional automatic page
  scrolling that pauses when you manually scroll away (both local engines).
- **◎ Jump to current sentence** in the player scrolls back to the spoken
  sentence without enabling automatic scrolling or changing playback. It also
  works while paused; it is disabled when no matching sentence is available.

## Build

The extension is built per-target from shared sources by `build.js`, which merges
`manifest.base.json` with the per-target override and copies `public/` + `src/`
into `dist-<target>/`.

```bash
npm install          # one-time: installs deepmerge (the only build dep)
npm run build:chrome     # -> dist-chrome/
npm run build:firefox    # -> dist-firefox/
```

## Install (unpacked / temporary)

This extension is not on any store yet, so it installs as an unpacked build.

**No build needed:** grab a prebuilt zip from the
[Releases](https://github.com/davuses/pagevoice/releases) page
(`pagevoice-extension-chrome.zip` / `pagevoice-extension-firefox.zip`), unzip it, and
load the unzipped folder using the steps below. The zips are produced
automatically for each tagged release — you only need the build commands if you
are developing or want an unreleased version.

**Chrome / Chromium / Edge**
1. `npm run build:chrome` (or unzip a release `pagevoice-extension-chrome.zip`).
2. Open `chrome://extensions`, enable **Developer mode**.
3. **Load unpacked** → select the `dist-chrome/` folder (or the unzipped folder).

**Firefox**
1. `npm run build:firefox` (or unzip a release `pagevoice-extension-firefox.zip`).
2. Open `about:debugging#/runtime/this-firefox`.
3. **Load Temporary Add-on** → select any file inside the folder
   (e.g. `manifest.json`). Or run `npm run start:firefox` (requires `web-ext`).

   Temporary add-ons are removed when Firefox restarts; permanent installation
   requires signing the build through [AMO](https://addons.mozilla.org/).

## Usage

1. Start [PageVoice Server](../server) (for Kokoro or Pocket).
2. Click the toolbar icon and pick an engine, then a voice. When a local engine is
   selected, a status line shows whether the server is reachable, and a
   **Local speech server URL** field lets you point at a non-default address.
   Models download/load on first use. Pocket does not expose synthesis-speed
   adjustment. Engine/voice changes apply to new reads; existing players keep
   their audio. Old combined Kokoro selections migrate automatically.
3. Read a page using the popup's **Read main article** / **Pick element to read**
   buttons, or the right-click context-menu items ("Read an element aloud…",
   "Read from here to the end", "Read main article aloud").

## Permissions

- `activeTab`, `<all_urls>` content script — to read the text you click/pick
  and to draw the in-page player and highlight.
- `contextMenus` — the right-click reading actions.
- `storage` — remembers your chosen engine/voice and server URL.
- `notifications` — surfaces TTS errors (e.g. server unreachable).

## Developer checks

```bash
npm test
npx playwright install chromium
npm run test:browser
```

The browser smoke test uses a temporary Chrome profile and a local fixture page.
Start PageVoice Server first; the test generates real speech with Pocket and
Kokoro and checks migration, engine switching, highlighting, scrolling,
sentence navigation, WAV download, and cleanup. `TTS_SERVER_URL` overrides the
default server URL, and `CHROMIUM_EXECUTABLE` can select an installed Chromium.
First use can download model weights; this test is opt-in and separate from
the fast settings tests.

## Privacy

See [PRIVACY.md](PRIVACY.md). In short: text you choose to read is sent either to
**your own** PageVoice Server, or — for the Google Translate engine — to Google's
public TTS endpoint. Nothing is collected or stored by the extension beyond your
local settings.

## License

[Apache-2.0](../LICENSE).
