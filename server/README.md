# PageVoice Server

A small [FastAPI](https://fastapi.tiangolo.com/) server that exposes the
[Kokoro](https://github.com/hexgrad/kokoro) and
[Pocket TTS](https://github.com/kyutai-labs/pocket-tts) models over HTTP.
Kokoro offers American/British English with adjustable synthesis speed. Pocket
offers 12 preset voices on CPU. Both stream PCM
and support the extension's highlighting, sentence skipping and auto-scroll.

It pairs with the companion [browser extension](../extension), which streams from
this server (default `http://localhost:18001`) — but the HTTP API is usable on
its own.

## Windows installer (recommended for non-technical users)

Windows users can install the server like a normal app: download
`kokoro-tts-server-setup.exe` from the
[Releases](https://github.com/davuses/kokoro-read-aloud/releases) page and run
it. The installer copies the server, sets up the `uv` toolchain and
dependencies (a few minutes, one time), adds Start Menu / optional desktop
shortcuts, and can **start automatically when you sign in**. It runs the server
in the background from a **system-tray icon** (right-click → *Quit* to stop) —
no console window to keep open.

The installer is small: the heavy ML dependencies and the model weights are
downloaded by the setup step / on first use, not bundled. The tray app lives in
[`tray.py`](tray.py); the installer is built from
[`installer/kokoro-server.iss`](installer/kokoro-server.iss) by the
`release-installer` CI workflow.

## Easy start (no command line)

If you prefer not to install anything, double-click the launcher for your system
inside the `server/` folder:

| System | File |
| --- | --- |
| Windows | `start-server.bat` |
| macOS | `start-server.command` |
| Linux | `start-server.sh` |

The first run installs the `uv` toolchain for you and downloads the speech model
(a few hundred MB), so it can take several minutes; later runs start quickly.
Keep the window open while you use the extension, and close it to stop the
server. The steps below are the manual equivalent for developers.

> macOS: the first time, right-click `start-server.command` → **Open** to get
> past Gatekeeper. Linux: if double-clicking doesn't offer "Run in Terminal",
> run `./start-server.sh` from a terminal.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)

Model weights and voice presets download automatically on first use. Internet
access is needed for the first read with each engine/voice; subsequent reads
use the local cache. Pocket uses `english_2026-10` with copied, cached preset
voice states. Custom voice uploads and cloning are not exposed.
These weights fix the training-data truncation of sentence-final numbers in
the older `english_2026-09_2` model ([upstream diagnosis](https://github.com/kyutai-labs/pocket-tts/issues/393),
[training fix](https://github.com/kyutai-labs/pocket-tts/pull/394)). Text is passed
unchanged and Pocket uses its default end-of-sequence policy.
Restart an already-running server after this change; loaded weights remain in
memory until it exits. `/engines` reports Pocket's selected `model` so the
running configuration can be checked.

## Setup

```bash
uv sync
```

### CPU vs GPU (NVIDIA)

By default this installs the **CPU** build of PyTorch — small, and fast enough
for typical use (Kokoro generates speech faster than real time on CPU). On
**Windows**, the CPU build is also what PyPI gives by default, so even a machine
with an NVIDIA GPU runs on CPU unless you opt in.

To use an **NVIDIA GPU**, install the CUDA build (~2.5 GB, CUDA 12.6):

```bash
uv sync --extra cuda
uv run --extra cuda python -m uvicorn server:app --host 0.0.0.0 --port 18001
```

The double-click launcher and the Windows installer ask **CPU or GPU** on first
run and remember the choice (a `gpu.flag` file). On Linux the default torch is
already CUDA-enabled, so the GPU is used without the extra. The server picks the
GPU automatically whenever a CUDA-capable torch is installed
([kokoro_model.py](kokoro_model.py): `"cuda" if torch.cuda.is_available()`).

## Running

```bash
uv run python -m uvicorn server:app --host 0.0.0.0 --port 18001
```

Port `18001` is what the companion kokoro-tts browser extension expects
(`http://localhost:18001/tts/stream`); change it only if you also update the
extension.

> Running uvicorn as a module (`python -m uvicorn`) rather than via the
> `uv run uvicorn` console-script shim avoids uv's *"trampoline failed to
> canonicalize script path"* error, which can occur on Windows when the project
> sits under a folder with non-ASCII characters (e.g. a Chinese username).

The HTTP server starts immediately. Models load lazily, so the first read with
an engine can take longer. `/health` reports HTTP readiness and each engine's
`loaded` state. Kokoro and Pocket share a serialized inference lock; closing a
player cancels generation and waits for the active worker before releasing it.

## Deployment

For others deploying this, the whole story is `uv` — there is **no Dockerfile by
design**:

- **GPU:** install a recent **NVIDIA driver**, then `uv sync`. You do *not* need a
  system CUDA toolkit — the PyTorch wheel bundles the CUDA runtime. The model uses
  the GPU automatically when `torch.cuda.is_available()`.
- **CPU:** no driver needed; it falls back to CPU automatically (slower, but
  works).
- **First run** downloads the Kokoro weights (~hundreds of MB), so the machine
  needs network access and a little disk on first use.
- **Optional:** the phonemizer workaround in [Notes](#notes) needs `espeak-ng`
  (`apt install espeak-ng`); the default path does not.

### Security

There is **no authentication or rate limiting** — anyone who can reach the port
can use your GPU. The `--host 0.0.0.0` in the example above exposes the server to
your whole network; bind to `127.0.0.1` instead if only the local machine (and
the extension) should reach it:

```bash
uv run uvicorn server:app --host 127.0.0.1 --port 18001
```

Requests are capped at 50,000 characters to keep a single call from holding the
inference lock indefinitely. If you expose this beyond a trusted network, put it
behind a reverse proxy that adds auth/rate limits and set `ALLOWED_ORIGINS`.

## Tests

```bash
uv run pytest
```

The tests mock inference, so they run without a GPU or model downloads.

### Shared Kokoro / Pocket dependency check

The shared environment pins NumPy 2.2.6 and Pocket TTS 4.0.1. Both engines are
selectable in the extension; Kokoro remains the default for older API clients.

To verify real inference from both libraries in the same Python process:

```bash
uv run python scripts/smoke_tts_environment.py
```

This downloads the model weights and Pocket's Alba preset on first use, checks
American and British Kokoro voices before and after Pocket streaming, and saves
WAV samples in a temporary directory for listening. It uses the explicit Pocket
model configuration `english_2026-10`; use `--output-dir PATH` to choose where
samples are written. This is an opt-in integration check, not part of pytest.

For repeatable sentence-ending comparisons (including the reported year 2026),
run `uv run python scripts/diagnose_pocket_endings.py`. It saves six seeds of
numeric, spelled-out, and ordinary sentences with sample counts and tail energy.
Use `--models english_2026-09_2 english_2026-10` to compare affected and retrained
weights, or `--voices alba anna michael` to compare specific presets. Listen to the
WAVs: a correct automatic transcript alone does not prove audible completion.

With the server running, `uv run python scripts/smoke_tts_api.py` additionally
checks real HTTP PCM from three Pocket presets, sentence boundaries, and
cancellation of a long read followed by a Kokoro request. Use `--server URL`
for a non-default address. It bypasses environment proxies so disconnects
reach the local server directly.

## API

### `GET /engines` and `GET /health`

`/engines` returns engine IDs, names, installation/loading state, and capability
flags (`speed`, `streaming`, `sentence_highlighting`). `/health` includes the
same catalog plus HTTP `ready` state. Catalog requests never load models.

### `GET /voices`

Returns the list of allowed voices — the single source of truth, so clients can
populate a dropdown instead of hardcoding the list:

```json
{
  "voices": [
    "af_bella", "af_heart", "af_sarah", "af_sky", "am_echo", "am_liam", "am_michael",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"
  ]
}
```

Cheap to call: it does not load the model.

`GET /voices?engine=pocket` lists Alba, Anna, Azelma, Bill Boerst, Charles,
Cosette, Eponine, Eve, George, Jane, Mary, and Michael.
Omitting `engine` preserves the original Kokoro response.

### `POST /tts/stream`

Request body:

```json
{ "text": "Hello from Kokoro", "voice": "af_bella", "speed": 1.0 }
```

`speed` is optional (default `1.0`, range `0.5`–`2.0`; out-of-range values
return `422`). Streams audio as it is generated for low-latency playback of long
text: an `application/x-ndjson` response with one JSON line per chunk —
`{"sr": 24000, "index": i, "pcm_b64": "<base64 Int16 mono PCM>", "text": "<the
grapheme text of this chunk>"}` — terminated by `{"done": true}`, or
`{"error": "..."}` on mid-stream failure. The `text` field lets a client align
on-screen highlighting to the audio. An empty `text` or an unknown `voice`
returns `400`.

Available voices: American English (recommended) — `af_bella`, `af_heart`,
`af_sarah`, `af_sky`, `am_echo`, `am_liam`, `am_michael`; British English —
`bf_alice`, `bf_emma`, `bf_isabella`, `bf_lily`, `bm_daniel`, `bm_fable`,
`bm_george`, `bm_lewis`.

Pocket request:

```json
{ "engine": "pocket", "voice": "alba", "text": "Hello world. Next sentence." }
```

`engine` defaults to `kokoro`. Pocket accepts only `speed: 1.0` (or omission);
other rates return `400`. Unknown engines/voices and blank text return `400`.
The sample rate always comes from the selected engine.

Pocket generates each sentence separately and emits these events in order:

```json
{"type":"sentence_start","sentence_id":0,"text":"Hello world."}
{"sr":24000,"index":0,"sentence_id":0,"pcm_b64":"..."}
{"type":"sentence_end","sentence_id":0}
```

There can be many PCM chunks per sentence. Sentence IDs are scoped to one HTTP
request. The player maps boundaries using cumulative PCM sample durations,
without repeating sentence text on every audio chunk. The stream ends with
`{"done":true}`; errors terminate it with `{"error":"..."}`. Separate sentence
generation can introduce pauses and has different prosody from full passages.

## Upgrading

Quit the existing tray server before running the new installer, then launch
PageVoice Server. A process already running on port 18001 continues to serve
its old code until restarted.

The Windows installer keeps the original AppId and `{localappdata}\KokoroTTSServer`
directory, but uses PageVoice labels and shortcuts. `dependency-version.txt`
causes the tray launcher to re-sync dependencies after upgrades; successful
setup records `.environment-ready`. Log paths and the Firefox extension ID
remain unchanged. Release assets retain their legacy `kokoro-*` filenames.
GPU/CPU preferences are retained during dependency upgrades. Run
`setup.bat --choose-device` to explicitly choose a different build on Windows.

## Configuration

- `ALLOWED_ORIGINS` — comma-separated CORS origins, e.g.
  `https://example.com,https://app.example.com`. Defaults to `*` (which, per
  the CORS spec, is served without credentials).

## Notes

The default misaki phonemizer occasionally mispronounces names (e.g. "Los
Angeles"). To work around it you can switch to `phonemizer` + `espeak-ng`:

```python
from phonemizer import phonemize

text = "Los Angeles is a sprawling city"
# 'en-us' gives American pronunciation, like the flapped 'T' in "city"
tokens = phonemize(
    text,
    backend="espeak",
    language="en-us",
    preserve_punctuation=True,
    with_stress=True,
)
```

## License

[Apache-2.0](../LICENSE). Kokoro is Apache-2.0, Pocket TTS is MIT. Preset voices
have separate terms in the [official catalog](https://huggingface.co/kyutai/tts-voices).
