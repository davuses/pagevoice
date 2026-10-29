"""Tests for the kokoro-server HTTP API.

These do not load the real Kokoro model: the streaming test monkeypatches
``stream_audio`` to yield fake PCM, so the suite runs on CPU-only / GPU-less
machines (e.g. CI) in milliseconds.
"""

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import kokoro_model
import engines as engines_module
from server import app

client = TestClient(app)


def test_voices_lists_allowed_voices():
    resp = client.get("/voices")
    assert resp.status_code == 200
    voices = resp.json()["voices"]
    assert voices == kokoro_model.kokoro_model.ALLOWED_VOICES
    assert "af_bella" in voices


def test_stream_empty_text_returns_400():
    resp = client.post("/tts/stream", json={"text": "", "voice": "af_bella"})
    assert resp.status_code == 400


def test_stream_unknown_voice_returns_400():
    resp = client.post("/tts/stream", json={"text": "hello", "voice": "no_such_voice"})
    assert resp.status_code == 400


def test_stream_emits_ndjson_chunks_then_done(monkeypatch):
    # Two ~10ms chunks of silence; never touches torch/the real pipeline.
    # stream_audio yields (text, audio) pairs.
    def fake_stream(text, voice, **kwargs):
        for i in range(2):
            yield f"Sentence {i}.", np.zeros(240, dtype=np.float32)

    monkeypatch.setattr(kokoro_model.kokoro_model, "stream_audio", fake_stream)

    resp = client.post("/tts/stream", json={"text": "hello", "voice": "af_bella"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/x-ndjson")

    lines = [json.loads(l) for l in resp.text.splitlines() if l]
    *chunks, last = lines
    assert last == {"done": True}
    assert len(chunks) == 2
    for i, chunk in enumerate(chunks):
        assert chunk["sr"] == kokoro_model.SAMPLE_RATE
        assert chunk["index"] == i
        assert chunk["pcm_b64"]
        assert chunk["text"] == f"Sentence {i}."


def test_stream_passes_speed_to_model(monkeypatch):
    seen = {}

    def fake_stream(text, voice, speed=1.0, **kwargs):
        seen["speed"] = speed
        yield "Hi.", np.zeros(240, dtype=np.float32)

    monkeypatch.setattr(kokoro_model.kokoro_model, "stream_audio", fake_stream)

    resp = client.post(
        "/tts/stream",
        json={"text": "hello", "voice": "af_bella", "speed": 1.5},
    )
    assert resp.status_code == 200
    assert seen["speed"] == 1.5


def test_stream_defaults_speed_when_omitted(monkeypatch):
    seen = {}

    def fake_stream(text, voice, speed=1.0, **kwargs):
        seen["speed"] = speed
        yield "Hi.", np.zeros(240, dtype=np.float32)

    monkeypatch.setattr(kokoro_model.kokoro_model, "stream_audio", fake_stream)

    resp = client.post("/tts/stream", json={"text": "hello", "voice": "af_bella"})
    assert resp.status_code == 200
    assert seen["speed"] == 1.0


def test_stream_rejects_out_of_range_speed():
    resp = client.post(
        "/tts/stream",
        json={"text": "hello", "voice": "af_bella", "speed": 5.0},
    )
    assert resp.status_code == 422


def test_preload_builds_a_pipeline_per_lang_code(monkeypatch):
    built = []
    monkeypatch.setattr(
        kokoro_model.kokoro_model,
        "_ensure_pipeline",
        lambda lang_code: built.append(lang_code),
    )
    kokoro_model.kokoro_model.preload()
    # Both the American ("a") and British ("b") pipelines are warmed.
    assert set(built) == {"a", "b"}


def test_voices_includes_british_voices():
    voices = client.get("/voices").json()["voices"]
    assert "bf_emma" in voices
    assert "bm_george" in voices


def test_stream_reports_generation_error_in_band(monkeypatch):
    def boom(text, voice, **kwargs):
        raise RuntimeError("kaboom")
        yield "", None  # make it a generator

    monkeypatch.setattr(kokoro_model.kokoro_model, "stream_audio", boom)

    resp = client.post("/tts/stream", json={"text": "hello", "voice": "af_bella"})
    # Status is already 200 by the time generation fails, so the error is
    # reported in-band as the final NDJSON line.
    assert resp.status_code == 200
    last = json.loads(resp.text.splitlines()[-1])
    assert "error" in last


def test_engine_catalog_and_legacy_voice_catalog():
    engines = {e["id"]: e for e in client.get("/engines").json()["engines"]}
    assert engines["kokoro"]["capabilities"]["speed"]
    assert not engines["pocket"]["capabilities"]["speed"]
    assert (
        client.get("/voices").json()["voices"]
        == engines_module.ENGINES["kokoro"].voices
    )
    assert "alba" in client.get("/voices?engine=pocket").json()["voices"]
    assert client.get("/voices?engine=unknown").status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"engine": "unknown", "voice": "alba", "text": "Hi"},
        {"engine": "pocket", "voice": "af_bella", "text": "Hi"},
        {"engine": "pocket", "voice": "alba", "text": "Hi", "speed": 1.5},
        {"engine": "pocket", "voice": "alba", "text": "  "},
        {"engine": "pocket", "voice": "alba", "text": "a" * 50_001},
        {"engine": "pocket", "voice": "https://example.com/voice.wav", "text": "Hi"},
    ],
)
def test_reject_invalid_engine_request(body):
    assert client.post("/tts/stream", json=body).status_code == 400


def test_pocket_sentence_events_and_sample_rate(monkeypatch):
    def stream(text, voice, speed, cancel):
        yield {"type": "sentence_start", "sentence_id": 0, "text": text}
        for _ in range(3):
            yield {
                "sr": 16000,
                "audio": np.ones(160, dtype=np.float32),
                "sentence_id": 0,
            }
        yield {"type": "sentence_end", "sentence_id": 0}

    monkeypatch.setattr(engines_module.ENGINES["pocket"], "stream", stream)
    result = client.post(
        "/tts/stream", json={"engine": "pocket", "voice": "alba", "text": "Hi."}
    )
    lines = [json.loads(line) for line in result.text.splitlines()]
    assert lines[0] == {"type": "sentence_start", "sentence_id": 0, "text": "Hi."}
    assert len(lines[1:-2]) == 3
    assert all(c["sr"] == 16000 and "text" not in c for c in lines[1:-2])
    assert lines[-2] == {"type": "sentence_end", "sentence_id": 0}
    assert lines[-1] == {"done": True}


@pytest.mark.parametrize(
    "first_sentence",
    [
        "Hello world.",
        "Nobody in math is ever going to forget the year 2026.",
    ],
)
def test_pocket_adapter_presets_streaming_and_cancellation(first_sentence):
    import threading
    from engines import PocketEngine

    class Audio:
        def detach(self):
            return self

        def cpu(self):
            return np.ones(240, dtype=np.float32)

    class Model:
        sample_rate = 24000

        def __init__(self):
            self.loaded_voices = []

        def get_state_for_audio_prompt(self, voice):
            self.loaded_voices.append(voice)
            return {"voice": voice}

        def generate_audio_stream(self, state, text, copy_state, stop, **kwargs):
            assert copy_state
            assert "frames_after_eos" not in kwargs
            if "year" in text:
                assert text == first_sentence
            for _ in range(3):
                if stop.is_set():
                    return
                yield Audio()

    engine = PocketEngine()
    engine.model = Model()
    cancel = threading.Event()
    events = list(engine.stream(first_sentence + " Next sentence!", "alba", 1, cancel))
    assert [e["text"] for e in events if e.get("type") == "sentence_start"] == [
        first_sentence,
        "Next sentence!",
    ]
    assert len([e for e in events if "audio" in e]) == 6
    stream = engine.stream("Hello again.", "alba", 1, cancel)
    next(stream)
    next(stream)
    cancel.set()
    assert list(stream) == []
    assert engine.model.loaded_voices == ["alba"]


def test_disconnect_stops_worker_and_releases_lock(monkeypatch):
    import asyncio
    import threading
    import time
    from server import TextRequest, tts_stream

    stopped = threading.Event()

    def stream(text, voice, speed, cancel):
        try:
            while not cancel.is_set():
                yield {"sr": 24000, "audio": np.ones(240, dtype=np.float32)}
                time.sleep(0.005)
        finally:
            stopped.set()

    class Request:
        calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    monkeypatch.setattr(engines_module.ENGINES["pocket"], "stream", stream)

    async def run():
        response = await tts_stream(
            TextRequest(engine="pocket", voice="alba", text="Hello"), Request()
        )
        await anext(response.body_iterator)
        await response.body_iterator.aclose()

    asyncio.run(run())
    assert stopped.wait(1)


def test_pocket_loads_retrained_weights_lazily(monkeypatch):
    import sys
    import threading
    import types
    from engines import PocketEngine

    loaded = []
    monkeypatch.setitem(sys.modules, "pocket_tts", types.SimpleNamespace(
        TTSModel=types.SimpleNamespace(load_model=lambda **kw: loaded.append(kw))))
    engine = PocketEngine()
    assert loaded == []
    cancel = threading.Event()
    cancel.set()
    assert list(engine.stream("The year 2026.", "alba", 1, cancel)) == []
    assert loaded == [{"language": "english_2026-10"}]
    pocket = next(e for e in client.get("/engines").json()["engines"] if e["id"] == "pocket")
    assert pocket["model"] == "english_2026-10"
