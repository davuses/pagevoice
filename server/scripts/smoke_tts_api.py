"""Opt-in real HTTP streaming/cancellation check; start PageVoice Server first."""

import argparse
import base64
import json
import time
import wave
from pathlib import Path
import httpx
import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--server", default="http://127.0.0.1:18001")
parser.add_argument("--output-dir", type=Path)
parser.add_argument("--cancel-timeout", type=float, default=15)
args = parser.parse_args()
if args.output_dir:
    args.output_dir.mkdir(parents=True, exist_ok=True)
# Bypass environment proxies so closing the client actually closes the server connection.
with httpx.Client(base_url=args.server, timeout=120, trust_env=False) as client:
    assert client.get("/health").raise_for_status().json()["ready"]
    assert {e["id"] for e in client.get("/engines").raise_for_status().json()["engines"]} == {"kokoro", "pocket"}
    assert "alba" in client.get("/voices", params={"engine": "pocket"}).raise_for_status().json()["voices"]
    for engine, voice in [
        ("pocket", "alba"),
        ("pocket", "anna"),
        ("pocket", "michael"),
        ("kokoro", "bf_emma"),
    ]:
        response = client.post(
            "/tts/stream",
            json={
                "engine": engine,
                "voice": voice,
                "text": "Hello world. This is another sentence.",
            },
        )
        response.raise_for_status()
        lines = [json.loads(l) for l in response.text.splitlines()]
        assert lines[-1] == {"done": True}, lines[-1]
        chunks = [l for l in lines if "pcm_b64" in l]
        assert chunks and any(
            np.frombuffer(base64.b64decode(l["pcm_b64"]), dtype="<i2").any()
            for l in chunks
        )
        if engine == "pocket":
            assert len([l for l in lines if l.get("type") == "sentence_start"]) == 2
            assert len([l for l in lines if l.get("type") == "sentence_end"]) == 2
        if args.output_dir:
            assert len({chunk["sr"] for chunk in chunks}) == 1
            with wave.open(str(args.output_dir / f"api-{engine}-{voice}.wav"), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(chunks[0]["sr"])
                output.writeframes(b"".join(base64.b64decode(chunk["pcm_b64"]) for chunk in chunks))
        print("PASS real API", engine, voice, len(chunks), flush=True)
    with client.stream(
        "POST",
        "/tts/stream",
        json={
            "engine": "pocket",
            "voice": "alba",
            "text": "This is a very long reading test. " * 400,
        },
    ) as stream:
        for line in stream.iter_lines():
            if "pcm_b64" in line:
                break
    started = time.monotonic()
    response = client.post(
        "/tts/stream",
        json={
            "engine": "kokoro",
            "voice": "af_bella",
            "text": "The next engine can speak.",
        },
    )
    assert json.loads(response.text.splitlines()[-1]) == {"done": True}
    assert time.monotonic() - started < args.cancel_timeout
    print("PASS real cancellation releases shared engine lock", flush=True)
