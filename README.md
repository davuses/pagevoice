# PageVoice

**English** | [简体中文](README.zh-CN.md)

Read web pages aloud with [Kokoro](https://github.com/hexgrad/kokoro) or
[Pocket TTS](https://github.com/kyutai-labs/pocket-tts) — a
self-hosted neural text-to-speech server plus a cross-browser extension that
streams from it, with a karaoke-style highlight that follows along as it reads.

This is a monorepo with two parts:

| Directory | What it is |
| --- | --- |
| [`server/`](server) | A shared FastAPI server for Kokoro (American/British English, adjustable speed) and Pocket TTS (English presets, CPU inference). |
| [`extension/`](extension) | A Chrome (MV3) / Firefox (MV2) extension that reads a page's main article, a clicked element, or from a clicked point to the end — via the server (Kokoro or Pocket TTS) or a zero-setup Google Translate fallback. |

The extension's Kokoro and Pocket engines need the server running; its Google Translate
engine does not.

![Demo: read main article aloud, with the karaoke highlight following along.](docs/demo.gif)

## Quickstart

> **Easiest install — Windows, no command line.** From the latest
> [release](https://github.com/davuses/pagevoice/releases):
>
> 1. Run **`kokoro-tts-server-setup.exe`**. It sets everything up (first run
>    downloads a few hundred MB, several minutes) and then runs the server from a
>    **system-tray icon** — can also start automatically when you sign in.
> 2. Unzip **`kokoro-extension-chrome.zip`**, open `chrome://extensions`, enable
>    *Developer mode*, and **Load unpacked** the unzipped folder.
> 3. Click the extension, choose Kokoro or Pocket TTS, select a voice, and read.
>
> The steps below are for macOS/Linux and for developers.

**1. Run the server** (see [`server/README.md`](server/README.md) for details):

Not comfortable with a terminal? Double-click the launcher for your system in
the `server/` folder — `start-server.bat` (Windows), `start-server.command`
(macOS), or `start-server.sh` (Linux) — and skip the commands below. It sets
everything up on first run.

```bash
cd server
uv sync
uv run uvicorn server:app --host 127.0.0.1 --port 18001
```

Each engine loads on its first request and caches its model and voices. First
use requires an internet connection to download weights. Kokoro uses the GPU
when available; Pocket runs on CPU. Both support streaming, sentence highlights,
auto-scroll, sentence skipping, and WAV downloads. Pocket currently offers
Alba, Anna, Azelma, Bill Boerst, Charles, Cosette, Eponine, Eve, George, Jane,
Mary, and Michael; synthesis-speed adjustment is Kokoro-only.

**2. Build and load the extension** (see [`extension/README.md`](extension/README.md)):

Don't want to build? Download a prebuilt zip from the
[Releases](https://github.com/davuses/pagevoice/releases) page, unzip it,
and load the folder (skip the commands below).

```bash
cd extension
npm install
npm run build:chrome     # or build:firefox
```

Then load the unpacked `dist-chrome/` (or `dist-firefox/`) in your browser, pick
an engine and voice in the popup, and use the popup's read buttons or the right-click
menu to read.

## Privacy & security at a glance

- Text you read with **Kokoro or Pocket TTS** goes only to the server you run yourself.
- Text you read with **Google Translate** is sent to Google's public TTS
  endpoint. See [`extension/PRIVACY.md`](extension/PRIVACY.md).
- The server has **no auth or rate limiting** — bind it to `127.0.0.1` unless you
  intend to share it. See the server README's security notes.

## License

[Apache-2.0](LICENSE). Kokoro is Apache-2.0; Pocket TTS is MIT. Voice presets
have their own upstream licenses; see the [voice catalog](https://huggingface.co/kyutai/tts-voices).

## Upgrading from kokoro-read-aloud

PageVoice is the new project name, hosted at [davuses/pagevoice](https://github.com/davuses/pagevoice).
Release asset names remain unchanged for compatibility. v3.0 requires updating both the server and
extension to use Pocket. Quit the old tray server before installing and restart
it afterward. Existing Kokoro voices, server URL, speed, look-ahead,
and auto-scroll settings are retained. Windows keeps the same installer AppId,
installation directory, GPU preference, and log location; the tray launcher
updates dependencies on first launch after an upgrade. Models load on demand.
