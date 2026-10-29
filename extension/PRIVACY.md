# Privacy

This extension reads text aloud. To do that it sends the text you explicitly
choose to read (a clicked element, the page from a clicked point, or detected
article content) to a
TTS service. It does **not** read, collect, transmit, or store anything else from
the pages you visit, and it has no analytics or telemetry.

## Where your text goes

It depends on the engine you select in the popup:

- **Kokoro or Pocket TTS** — the text is sent to PageVoice Server you run yourself, at the URL
  configured in the popup (default `http://localhost:18001`). This is your own
  machine/server; no third party is involved. The server generates audio and
  streams it back.
- **Google Translate** — the text is sent to Google's public translate
  text-to-speech endpoint (`https://www.google.com/speech-api/...`) to fetch the
  audio. This means **the text you read is sent to Google** and is subject to
  Google's privacy policy. Use either local engine to keep text on your server.

Text is sent only at the moment you trigger a read action. It is sent for
synthesis only and is not used by the extension for any other purpose.

## What is stored

The extension stores only your settings via the browser's extension storage
(`storage.sync`): the selected engine, voices per engine, server URL, speed,
look-ahead and auto-scroll preferences. These stay
in your browser profile (synced by the browser if you have sync enabled). No
audio, no page content, and no reading history are stored.

The local server downloads model weights and preset voice embeddings from
Hugging Face on first use and caches them locally. Reading text is not sent
with those downloads. This release does not accept uploaded/cloned voices.

## Permissions

The host/content-script permissions exist solely to read the text you ask it to
read and to draw the in-page audio player and highlight. See the README for the
per-permission rationale.
